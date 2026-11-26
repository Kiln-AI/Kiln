"""The answers of the model info endpoints. Pure functions.

Each answer joins the model catalogue (Kiln's model list with the models.dev
facts) with what Kiln offers now: one `/api/available_models` payload
(`Offered`). The payload decides what the user can run; the catalogue adds
prices, limits, dates, notes and tags. For an offered pair the thinking
levels and the output mode come from the payload, which applies the user's
overrides and the local runtimes' forced modes.
"""

import difflib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.desktop.studio_server.api_models.model_info_models import (
    ModelInfoDetails,
    ModelInfoList,
    ModelInfoProviderEntryDetails,
    ModelInfoProviderEntryRow,
    ModelInfoProviderList,
    ModelInfoProviderRow,
    ModelInfoRow,
    ModelInfoSources,
    ModelInfoStatus,
)
from app.desktop.studio_server.services.model_info.catalog_build import (
    kiln_suggested_for,
)
from app.desktop.studio_server.services.model_info.catalog_schema import (
    Catalog,
    CatalogEntry,
    CatalogModel,
)

Pair = tuple[str, str]  # (Kiln provider id, Kiln model id)
ModelSort = Literal["featured", "price", "newest"]

TYPO_MIN_RATIO = 0.75
CLOSEST_IDS = 3


class ModelNotFoundError(Exception):
    """No model, or no entry for the provider. The text is for the caller."""


class InvalidModelQueryError(Exception):
    """A query that cannot be answered. The text is for the caller."""


@dataclass(frozen=True)
class ListModelsQuery:
    """The parameters of `GET /api/model_info/models`."""

    search: str | None = None
    featured: bool | None = None
    provider: str | None = None
    family: str | None = None
    tags: tuple[str, ...] | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    has_thinking_levels: bool | None = None
    reasoning_model: bool | None = None
    open_weights: bool | None = None
    include_not_available: bool = False
    include_deprecated: bool = False
    include_notes: bool = False
    sort: ModelSort | None = None
    limit: int = 25
    offset: int = 0


@dataclass(frozen=True)
class Offered:
    """What Kiln offers now: from one `/api/available_models` payload."""

    pairs: dict[Pair, dict[str, Any]]  # (provider, model) -> the model dict
    connected: frozenset[str]  # provider ids in the payload
    order: list[Pair]  # the payload's order

    @classmethod
    def from_payload(cls, payload: Any) -> "Offered":
        pairs: dict[Pair, dict[str, Any]] = {}
        connected: set[str] = set()
        for provider_entry in payload if isinstance(payload, list) else []:
            if not isinstance(provider_entry, dict):
                continue
            provider = provider_entry.get("provider_id")
            if not isinstance(provider, str) or not provider:
                continue
            connected.add(provider)
            for model in provider_entry.get("models") or []:
                if isinstance(model, dict) and isinstance(model.get("id"), str):
                    pairs.setdefault((provider, model["id"]), model)
        return cls(pairs=pairs, connected=frozenset(connected), order=list(pairs))


def status(offered: Offered, provider: str, model: str) -> ModelInfoStatus:
    if (provider, model) in offered.pairs:
        return "ready"
    if provider in offered.connected:
        return "not_offered"
    return "not_connected"


# ---- the merged view: the catalogue, and what only the payload knows


def _flag(d: dict[str, Any], key: str) -> bool | None:
    value = d.get(key)
    return value if isinstance(value, bool) else None


def _text(d: dict[str, Any], key: str) -> str | None:
    value = d.get(key)
    return value if isinstance(value, str) and value else None


def _offered_thinking_levels(d: dict[str, Any]) -> list[str]:
    levels = d.get("available_thinking_levels")
    return [str(v) for v in levels.values()] if isinstance(levels, dict) else []


def _take_offered_fields(entry: CatalogEntry, d: dict[str, Any]) -> None:
    entry.thinking_levels = _offered_thinking_levels(d)
    entry.default_thinking_level = _text(d, "default_thinking_level")
    entry.default_structured_output_mode = _text(d, "structured_output_mode")


def _entry_from_offered(provider: str, d: dict[str, Any]) -> CatalogEntry:
    """An entry for a pair the catalogue does not have (a fine-tune, a custom
    model, a model newer than the installed list). The models.dev fields stay
    null."""
    return CatalogEntry(
        provider=provider,
        deprecated=d.get("deprecated") is True,
        untested=d.get("untested_model") is True,
        supports_tools=_flag(d, "supports_function_calling"),
        supports_structured_output=_flag(d, "supports_structured_output"),
        supports_vision=_flag(d, "supports_vision"),
        kiln_suggested_for=kiln_suggested_for(d),
        thinking_levels=_offered_thinking_levels(d),
        default_thinking_level=_text(d, "default_thinking_level"),
        default_structured_output_mode=_text(d, "structured_output_mode"),
    )


def _merged(catalog: Catalog, offered: Offered) -> list[CatalogModel]:
    """The catalogue's models in its order, each with an entry added for each
    offered pair the catalogue lacks; then the models only the payload has, by
    model id. The catalogue itself is not changed."""
    rows = [row.model_copy(deep=True) for row in catalog.models]
    by_id = {row.model: row for row in rows}
    known = {(e.provider, row.model): e for row in rows for e in row.entries}
    offered_only: dict[str, list[Pair]] = {}
    for pair in offered.order:
        provider, model = pair
        if pair in known:
            _take_offered_fields(known[pair], offered.pairs[pair])
        elif model in by_id:
            by_id[model].entries.append(
                _entry_from_offered(provider, offered.pairs[pair])
            )
        else:
            offered_only.setdefault(model, []).append(pair)
    for model in sorted(offered_only):
        pairs = offered_only[model]
        first = offered.pairs[pairs[0]]
        rows.append(
            CatalogModel(
                model=model,
                display_name=_text(first, "name") or model,
                entries=[
                    _entry_from_offered(p, offered.pairs[(p, model)]) for p, _ in pairs
                ],
            )
        )
    return rows


def _provider_ids(catalog: Catalog, offered: Offered) -> list[str]:
    """Kiln's providers, then the providers of the catalogue's entries, then
    the connected ones, without duplicates."""
    return list(
        dict.fromkeys(
            [
                *(p.provider for p in catalog.providers),
                *(e.provider for row in catalog.models for e in row.entries),
                *sorted(offered.connected),
            ]
        )
    )


def _has_thinking_levels(entries: Sequence[CatalogEntry]) -> bool:
    return any(e.thinking_levels for e in entries)


# ---- name search


def _spaced(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _squashed(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _match_rank(query: str, words: list[str], row: CatalogModel) -> int | None:
    model_id, name = _squashed(row.model), _squashed(row.display_name)
    if query in (model_id, name):
        return 0
    if model_id.startswith(query) or name.startswith(query):
        return 1
    if query in model_id or query in name:
        return 2
    spaced_text = f"{_spaced(row.model)} {_spaced(row.display_name)}"
    squashed_text = f"{model_id} {name}"
    if all(word in spaced_text or word in squashed_text for word in words):
        return 3
    return None


def _typo_ratio(query: str, row: CatalogModel) -> float:
    return max(
        difflib.SequenceMatcher(None, query, _squashed(row.model)).ratio(),
        difflib.SequenceMatcher(None, query, _squashed(row.display_name)).ratio(),
    )


def search_rows(
    query: str, rows: Sequence[CatalogModel]
) -> tuple[list[CatalogModel], bool]:
    """The rows whose id or name matches `query`, best first; ties keep the
    order of `rows`. With no match, the rows with a close name (a typo), and
    True."""
    squashed = _squashed(query)
    if not squashed:
        raise InvalidModelQueryError("search needs at least one letter or digit.")
    words = _spaced(query).split()
    ranked = [
        (rank, row)
        for row in rows
        if (rank := _match_rank(squashed, words, row)) is not None
    ]
    if ranked:
        ranked.sort(key=lambda r: r[0])
        return [row for _, row in ranked], False
    close = [
        (ratio, row)
        for row in rows
        if (ratio := _typo_ratio(squashed, row)) >= TYPO_MIN_RATIO
    ]
    close.sort(key=lambda r: -r[0])
    return [row for _, row in close], bool(close)


# ---- list_models


def _keeps(
    entry: CatalogEntry, entry_status: ModelInfoStatus, query: ListModelsQuery
) -> bool:
    """The entry filters. An entry with a null value for a filter it is
    tested on does not pass."""
    if entry_status != "ready" and not query.include_not_available:
        return False
    if entry.deprecated and not query.include_deprecated:
        return False
    if query.provider is not None and entry.provider != query.provider:
        return False
    for wanted, actual in (
        (query.supports_tools, entry.supports_tools),
        (query.supports_vision, entry.supports_vision),
        (query.has_thinking_levels, bool(entry.thinking_levels)),
    ):
        if wanted is not None and actual is not wanted:
            return False
    return True


def _row_keeps(
    row: CatalogModel, entries: list[CatalogEntry], query: ListModelsQuery
) -> bool:
    if not entries:
        return False
    if query.family is not None and row.family != query.family:
        return False
    for wanted, actual in (
        (query.open_weights, row.open_weights),
        (query.reasoning_model, row.reasoning_model),
    ):
        if wanted is not None and actual is not wanted:
            return False
    if (
        query.featured is not None
        and (row.kiln_featured_rank is not None) is not query.featured
    ):
        return False
    if query.tags:
        tags = set(row.tags).union(*(e.tags for e in entries))
        if not tags & set(query.tags):
            return False
    return True


def _price_key(row: CatalogModel, entries: list[CatalogEntry]) -> float:
    """The median input + output price; else the cheapest listed entry. A $0
    price is a free tier, not what the model costs, so it never sorts."""
    if row.median_input_price is not None and row.median_output_price is not None:
        return row.median_input_price + row.median_output_price
    prices = [
        e.input_price + e.output_price
        for e in entries
        if e.input_price and e.output_price
    ]
    return min(prices, default=math.inf)


def _newest_key(row: CatalogModel) -> tuple[bool, int]:
    try:
        ordinal = date.fromisoformat(row.release_date or "").toordinal()
    except ValueError:
        return (True, 0)
    return (False, -ordinal)


def _featured_key(row: CatalogModel) -> tuple[bool, int]:
    return (row.kiln_featured_rank is None, row.kiln_featured_rank or 0)


Kept = tuple[CatalogModel, list[tuple[CatalogEntry, ModelInfoStatus]]]


def list_models(
    catalog: Catalog,
    offered: Offered,
    sources: ModelInfoSources,
    query: ListModelsQuery,
) -> ModelInfoList:
    if query.provider is not None:
        known = _provider_ids(catalog, offered)
        if query.provider not in known:
            raise InvalidModelQueryError(
                f"Unknown provider: {query.provider}. Provider ids: {', '.join(sorted(known))}."
            )
    kept: list[Kept] = []
    for row in _merged(catalog, offered):
        entries: list[tuple[CatalogEntry, ModelInfoStatus]] = [
            (e, s)
            for e in row.entries
            if _keeps(e, s := status(offered, e.provider, row.model), query)
        ]
        if _row_keeps(row, [e for e, _ in entries], query):
            kept.append((row, entries))
    # The merged rows are in Kiln's order, then the payload-only models by id.
    # Every sort is stable, so each one keeps the featured order for its ties.
    kept.sort(key=lambda r: _featured_key(r[0]))
    fuzzy = False
    if query.search is not None:
        matched, fuzzy = search_rows(query.search, [row for row, _ in kept])
        position = {id(row): i for i, row in enumerate(matched)}
        kept = [r for r in kept if id(r[0]) in position]
        if query.sort is None:
            kept.sort(key=lambda r: position[id(r[0])])
    if query.sort == "price":
        kept.sort(key=lambda r: _price_key(r[0], [e for e, _ in r[1]]))
    elif query.sort == "newest":
        kept.sort(key=lambda r: _newest_key(r[0]))
    page = kept[query.offset : query.offset + query.limit]
    return ModelInfoList(
        sources=sources,
        total=len(kept),
        fuzzy_match=fuzzy,
        models=[_model_row(row, entries, query.include_notes) for row, entries in page],
    )


def _model_row(
    row: CatalogModel,
    entries: list[tuple[CatalogEntry, ModelInfoStatus]],
    include_notes: bool,
) -> ModelInfoRow:
    return ModelInfoRow(
        model=row.model,
        display_name=row.display_name,
        family=row.family,
        kiln_featured_rank=row.kiln_featured_rank,
        tags=row.tags,
        release_date=row.release_date,
        context_window=row.context_window,
        open_weights=row.open_weights,
        reasoning_model=row.reasoning_model,
        has_thinking_levels=_has_thinking_levels([e for e, _ in entries]),
        median_input_price=row.median_input_price,
        median_output_price=row.median_output_price,
        editorial_notes=row.editorial_notes if include_notes else None,
        agent_notes=row.agent_notes if include_notes else None,
        providers=[
            ModelInfoProviderEntryRow(
                provider=e.provider,
                status=s,
                input_price=e.input_price,
                output_price=e.output_price,
                tags=e.tags,
                deprecated=e.deprecated,
            )
            for e, s in entries
        ],
    )


# ---- model_details


def _find_model(rows: list[CatalogModel], model_id: str) -> CatalogModel:
    """The row with this id; else the only row with this id in another case."""
    exact = next((r for r in rows if r.model == model_id), None)
    if exact is not None:
        return exact
    folded = [r for r in rows if r.model.casefold() == model_id.casefold()]
    if len(folded) == 1:
        return folded[0]
    message = f"Model not found: {model_id}."
    closest = _closest_ids(model_id, rows)
    if closest:
        message += f" Closest ids: {', '.join(closest)}."
    message += (
        " To find a model id, call GET /api/model_info/models with search=<name>"
        " and include_not_available=true."
    )
    raise ModelNotFoundError(message)


def _closest_ids(model_id: str, rows: list[CatalogModel]) -> list[str]:
    try:
        matched, _ = search_rows(model_id, rows)
    except InvalidModelQueryError:
        return []
    return [row.model for row in matched[:CLOSEST_IDS]]


def model_details(
    catalog: Catalog,
    offered: Offered,
    sources: ModelInfoSources,
    model_id: str,
    provider: str | None,
) -> ModelInfoDetails:
    row = _find_model(_merged(catalog, offered), model_id)
    entries = row.entries
    if provider is not None:
        entries = [e for e in row.entries if e.provider == provider]
        if not entries:
            providers = ", ".join(dict.fromkeys(e.provider for e in row.entries))
            raise ModelNotFoundError(
                f"Model {row.model} has no entry for provider {provider}."
                f" Its providers: {providers}."
            )
    return ModelInfoDetails(
        sources=sources,
        model=row.model,
        display_name=row.display_name,
        family=row.family,
        kiln_featured_rank=row.kiln_featured_rank,
        tags=row.tags,
        release_date=row.release_date,
        release_date_estimated=row.release_date_estimated,
        knowledge_cutoff=row.knowledge_cutoff,
        context_window=row.context_window,
        max_output_tokens=row.max_output_tokens,
        open_weights=row.open_weights,
        reasoning_model=row.reasoning_model,
        has_thinking_levels=_has_thinking_levels(entries),
        median_input_price=row.median_input_price,
        median_output_price=row.median_output_price,
        editorial_notes=row.editorial_notes,
        agent_notes=row.agent_notes,
        providers=[
            _entry_details(e, status(offered, e.provider, row.model)) for e in entries
        ],
    )


def _entry_details(
    entry: CatalogEntry, entry_status: ModelInfoStatus
) -> ModelInfoProviderEntryDetails:
    return ModelInfoProviderEntryDetails(
        provider=entry.provider,
        status=entry_status,
        provider_model_id=entry.provider_model_id,
        deprecated=entry.deprecated,
        untested=entry.untested,
        input_price=entry.input_price,
        output_price=entry.output_price,
        cache_read_price=entry.cache_read_price,
        cache_write_price=entry.cache_write_price,
        context_window=entry.context_window,
        max_output_tokens=entry.max_output_tokens,
        tags=entry.tags,
        supports_tools=entry.supports_tools,
        supports_structured_output=entry.supports_structured_output,
        supports_vision=entry.supports_vision,
        supports_temperature=entry.supports_temperature,
        thinking_levels=entry.thinking_levels,
        default_thinking_level=entry.default_thinking_level,
        default_structured_output_mode=entry.default_structured_output_mode,
        kiln_suggested_for=entry.kiln_suggested_for,
    )


# ---- list_providers


def list_providers(
    catalog: Catalog, offered: Offered, sources: ModelInfoSources
) -> ModelInfoProviderList:
    ready: dict[str, int] = {}
    for provider, _ in offered.pairs:
        ready[provider] = ready.get(provider, 0) + 1
    rows = []
    for provider in _provider_ids(catalog, offered):
        info = catalog.provider(provider)
        rows.append(
            ModelInfoProviderRow(
                provider=provider,
                name=info.name if info else None,
                status="connected"
                if provider in offered.connected
                else "not_connected",
                ready_model_count=ready.get(provider, 0),
                tags=info.tags if info else [],
                notes=info.notes if info else None,
            )
        )
    rows.sort(key=lambda r: (-r.ready_model_count, r.provider))
    return ModelInfoProviderList(sources=sources, providers=rows)
