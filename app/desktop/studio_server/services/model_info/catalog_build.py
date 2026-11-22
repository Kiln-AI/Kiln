"""The catalogue build: Kiln's model list, with models.dev joined on. Pure: no
I/O.

The join gives the price and limits of each (provider, model) pair, and the
model facts from the first matched entry in a fixed provider order. When no
entry gives a release date, the date is looked up across all of models.dev by
a loose key. The median price of a model is taken across all of models.dev, by
the model's canonical id: one provider's price can be far from what most
providers charge.
"""

import json
import math
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from kiln_ai.adapters.ml_model_list import KilnModel, KilnModelProvider
from kiln_ai.adapters.ml_provider_list import KilnProviderInfo

from app.desktop.studio_server.services.model_info.catalog_schema import (
    Catalog,
    CatalogEntry,
    CatalogModel,
    CatalogProvider,
)

NOTE_LIMIT = 2000
CUT_MARK = " [cut]"
MAX_TAGS = 12
_TAG_RE = re.compile(r"[a-z0-9_]{1,40}")
# A short key such as `o3` matches too much.
MIN_LOOSE_KEY = 4
# Kiln's `suggested_for_<flag>` -> the value in `kiln_suggested_for`.
KILN_SUGGESTED_FOR: dict[str, str] = {
    "evals": "eval_judge",
    "data_gen": "synthetic_data",
    "doc_extraction": "document_extraction",
    "synthetic_user": "synthetic_user",
}
_SUGGESTED_FOR_FIELDS = frozenset(
    f"suggested_for_{flag}" for flag in KILN_SUGGESTED_FOR
)
# A median over fewer providers is too easy to move with one odd price.
MIN_MEDIAN_PRICES = 3
# The providers whose models.dev entry gives a model's facts first.
PREFERENCE: tuple[str, ...] = (
    "openrouter",
    "openai",
    "anthropic",
    "gemini_api",
    "groq",
    "together_ai",
)

# The keys of a models.dev entry that the join reads. The rest of the
# document (about 26 MB parsed) is dropped.
_COST_KEYS = ("input", "output", "cache_read", "cache_write")
_LIMIT_KEYS = ("context", "output")
_FACT_KEYS = (
    "temperature",
    "release_date",
    "knowledge",
    "open_weights",
    "reasoning",
    "canonical_model_id",
)


@dataclass(frozen=True)
class KilnModelList:
    """Kiln's side of the join, as the process holds it now."""

    models: tuple[KilnModel, ...]
    providers: tuple[KilnProviderInfo, ...]
    # The last good remote model list load; None: the list shipped with the app.
    loaded_at: datetime | None


@dataclass
class Prices:
    """The positive prices of one canonical model id: models.dev provider id
    -> that provider's lowest price. A provider can list one model more than
    once (an alias, a region, a fast tier), and it counts once."""

    input: dict[str, float] = field(default_factory=dict)
    output: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelsDevData:
    """models.dev's document in its own nesting (provider -> "models" ->
    model id -> entry), with only the keys the join reads, and two indexes
    over all of it."""

    providers: Mapping[str, Any]
    loose_dates: Mapping[str, str]  # loose key -> earliest release date
    canonical_prices: Mapping[str, Prices]  # canonical model id -> prices


def parse_models_dev(body: bytes) -> ModelsDevData:
    """The slim form of models.dev's `api.json`. Raises `ValueError("not valid
    JSON")` or `ValueError("not an object")`."""
    try:
        raw = json.loads(body)
    except (ValueError, RecursionError):
        raise ValueError("not valid JSON") from None
    if not isinstance(raw, Mapping):
        raise ValueError("not an object")
    providers: dict[str, Any] = {}
    for provider_id, provider in raw.items():
        models = _mapping(_mapping(provider).get("models"))
        providers[provider_id] = {
            "models": {
                model_id: _slim_entry(md)
                for model_id, md in models.items()
                if isinstance(md, Mapping)
            }
        }
    return ModelsDevData(
        providers=providers,
        loose_dates=_loose_index(providers),
        canonical_prices=_canonical_price_index(providers),
    )


def _slim_entry(md: Mapping[str, Any]) -> dict[str, Any]:
    slim = {key: md[key] for key in _FACT_KEYS if key in md}
    for name, keys in (("cost", _COST_KEYS), ("limit", _LIMIT_KEYS)):
        if isinstance(part := md.get(name), Mapping):
            slim[name] = {key: part[key] for key in keys if key in part}
    return slim


def build_catalog(kiln: KilnModelList, models_dev: ModelsDevData | None) -> Catalog:
    """The catalogue of Kiln's models, with the models.dev facts when
    `models_dev` is given. A duplicate model name keeps the first model."""
    providers = _provider_list(kiln.providers)
    published = {p.provider: p.models_dev_id for p in providers}
    models: list[CatalogModel] = []
    seen: set[str] = set()
    for kiln_model in kiln.models:
        if kiln_model.name in seen:
            continue
        seen.add(kiln_model.name)
        model = _model(kiln_model)
        if models_dev is not None:
            _join(model, models_dev, published)
        models.append(model)
    return Catalog(models=models, providers=providers)


# ---- Kiln's side ----


def kiln_suggested_for(flags: Mapping[str, Any]) -> list[str]:
    """The `kiln_suggested_for` values of Kiln's `suggested_for_*` flags, of
    a Kiln provider entry or of an `/api/available_models` model dict."""
    return [
        value
        for flag, value in KILN_SUGGESTED_FOR.items()
        if flags.get(f"suggested_for_{flag}") is True
    ]


def _tags(values: Sequence[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        if isinstance(value, str) and _TAG_RE.fullmatch(value) and value not in tags:
            tags.append(value)
            if len(tags) == MAX_TAGS:
                break
    return tags


def _note(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    if len(text) <= NOTE_LIMIT:
        return text
    return text[: NOTE_LIMIT - len(CUT_MARK)].rstrip() + CUT_MARK


def _provider_list(infos: Sequence[KilnProviderInfo]) -> list[CatalogProvider]:
    providers: list[CatalogProvider] = []
    seen: set[str] = set()
    for info in infos:
        if info.id.value in seen:
            continue
        seen.add(info.id.value)
        providers.append(
            CatalogProvider(
                provider=info.id.value,
                name=info.friendly_name,
                notes=_note(info.notes),
                tags=_tags(info.tags),
                models_dev_id=info.models_dev_id,
            )
        )
    return providers


def _model(model: KilnModel) -> CatalogModel:
    return CatalogModel(
        model=model.name,
        display_name=model.friendly_name or model.name,
        family=model.family or None,
        kiln_featured_rank=model.featured_rank,
        editorial_notes=_note(model.editorial_notes),
        agent_notes=_note(model.agent_notes),
        tags=_tags(model.tags),
        entries=[_entry(provider) for provider in model.providers],
    )


def _entry(provider: KilnModelProvider) -> CatalogEntry:
    return CatalogEntry(
        provider=provider.name.value,
        provider_model_id=provider.model_id,
        deprecated=provider.deprecated,
        untested=provider.untested_model,
        supports_tools=provider.supports_function_calling,
        supports_structured_output=provider.supports_structured_output,
        supports_vision=provider.supports_vision,
        thinking_levels=list((provider.available_thinking_levels or {}).values()),
        default_thinking_level=provider.default_thinking_level,
        default_structured_output_mode=provider.structured_output_mode.value,
        kiln_suggested_for=kiln_suggested_for(
            provider.model_dump(include=set(_SUGGESTED_FOR_FIELDS))
        ),
        tags=_tags(provider.tags),
    )


# ---- the models.dev join ----


def _price(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        price = float(value)
    except OverflowError:
        return None
    if not math.isfinite(price) or price < 0:
        return None
    return price


def _limit(value: Any) -> int | None:
    """A bool is not an int here."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _models_dev_entry(
    providers: Mapping[str, Any], md_provider: str | None, model_id: str | None
) -> Mapping[str, Any] | None:
    if md_provider is None or model_id is None:
        return None
    models = _mapping(_mapping(providers.get(md_provider)).get("models"))
    entry = models.get(model_id)
    return entry if isinstance(entry, Mapping) else None


def _preference_rank(entry: CatalogEntry) -> tuple[int, str]:
    """`PREFERENCE` first, then the other providers by id."""
    if entry.provider in PREFERENCE:
        return PREFERENCE.index(entry.provider), ""
    return len(PREFERENCE), entry.provider


def _join(
    model: CatalogModel,
    models_dev: ModelsDevData,
    published: Mapping[str, str | None],
) -> None:
    matched: list[tuple[CatalogEntry, Mapping[str, Any]]] = []
    for entry in model.entries:
        md = _models_dev_entry(
            models_dev.providers,
            published.get(entry.provider),
            entry.provider_model_id,
        )
        if md is None:
            continue
        matched.append((entry, md))
        cost = _mapping(md.get("cost"))
        limit = _mapping(md.get("limit"))
        entry.input_price = _price(cost.get("input"))
        entry.output_price = _price(cost.get("output"))
        entry.cache_read_price = _price(cost.get("cache_read"))
        entry.cache_write_price = _price(cost.get("cache_write"))
        entry.context_window = _limit(limit.get("context"))
        entry.max_output_tokens = _limit(limit.get("output"))
        temperature = md.get("temperature")
        entry.supports_temperature = (
            temperature if isinstance(temperature, bool) else None
        )

    if matched:
        matched.sort(key=lambda pair: _preference_rank(pair[0]))
        first = matched[0][1]
        limit = _mapping(first.get("limit"))
        model.release_date = _iso_date(first.get("release_date"))
        knowledge = first.get("knowledge")
        model.knowledge_cutoff = knowledge if isinstance(knowledge, str) else None
        open_weights = first.get("open_weights")
        model.open_weights = open_weights if isinstance(open_weights, bool) else None
        reasoning = first.get("reasoning")
        model.reasoning_model = reasoning if isinstance(reasoning, bool) else None
        model.context_window = _limit(limit.get("context"))
        model.max_output_tokens = _limit(limit.get("output"))
        _set_median_prices(
            model, [md for _, md in matched], models_dev.canonical_prices
        )
    if model.release_date is None:
        model.release_date = _loose_date(model, models_dev.loose_dates)
        model.release_date_estimated = model.release_date is not None


# ---- the median price ----


def _paid(value: Any) -> float | None:
    """A price for the median: a $0 price is usually a free tier or a plan,
    not what most providers charge."""
    price = _price(value)
    return price if price else None


def _keep_lowest(prices: dict[str, float], provider: str, value: Any) -> None:
    price = _paid(value)
    if price is not None and price < prices.get(provider, math.inf):
        prices[provider] = price


def _canonical_price_index(providers: Mapping[str, Any]) -> dict[str, Prices]:
    index: dict[str, Prices] = {}
    for provider_id, provider in providers.items():
        for md in _mapping(_mapping(provider).get("models")).values():
            if not isinstance(md, Mapping):
                continue
            canonical = md.get("canonical_model_id")
            if not isinstance(canonical, str) or not canonical:
                continue
            cost = _mapping(md.get("cost"))
            prices = index.setdefault(canonical, Prices())
            _keep_lowest(prices.input, provider_id, cost.get("input"))
            _keep_lowest(prices.output, provider_id, cost.get("output"))
    return index


def _median(by_provider: dict[str, float]) -> float | None:
    if len(by_provider) < MIN_MEDIAN_PRICES:
        return None
    return statistics.median(by_provider.values())


def _set_median_prices(
    model: CatalogModel,
    matched: list[Mapping[str, Any]],
    canonical_prices: Mapping[str, Prices],
) -> None:
    """The median of the canonical id of the first matched entry that has
    one. `matched` is in the provider preference order."""
    canonical = next(
        (
            c
            for md in matched
            if isinstance(c := md.get("canonical_model_id"), str) and c
        ),
        None,
    )
    prices = canonical_prices.get(canonical) if canonical is not None else None
    if prices is None:
        return
    model.median_input_price = _median(prices.input)
    model.median_output_price = _median(prices.output)


# ---- the loose release date ----


def _key(model_id: str) -> str:
    tail = model_id.split("/")[-1].split(":")[0].lower()
    return re.sub(r"[^a-z0-9]", "", tail)


def _loose_index(providers: Mapping[str, Any]) -> dict[str, str]:
    """Loose key -> the earliest valid release date among the models.dev
    entries with that key. An early date is the first release; a later date
    on a key is usually a provider adding the model later."""
    index: dict[str, str] = {}
    for provider in providers.values():
        for model_id, md in _mapping(_mapping(provider).get("models")).items():
            if not isinstance(md, Mapping):
                continue
            released = _iso_date(md.get("release_date"))
            if released is None:
                continue
            ids = [model_id, md.get("canonical_model_id")]
            for key in {_key(i) for i in ids if isinstance(i, str)}:
                if len(key) < MIN_LOOSE_KEY:
                    continue
                if key not in index or released < index[key]:
                    index[key] = released
    return index


def _loose_date(model: CatalogModel, loose_dates: Mapping[str, str]) -> str | None:
    # Deprecated entries count: an old id is still evidence of the release.
    dates = [
        loose_dates[key]
        for entry in model.entries
        if entry.provider_model_id is not None
        and len(key := _key(entry.provider_model_id)) >= MIN_LOOSE_KEY
        and key in loose_dates
    ]
    return min(dates, default=None)
