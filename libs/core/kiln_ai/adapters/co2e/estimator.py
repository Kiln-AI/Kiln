"""Runtime CO2e estimation from the committed factor table.

Lookup is keyed by (kiln_model_name, provider, serving_tier, region_mode) —
the same ModelName / ModelProviderName strings used across Kiln. Missing
(model, provider) pairs return None gracefully: an absent factor is honest
absence, never a fabricated default.
"""

import json
from functools import cache
from pathlib import Path

from kiln_ai.adapters.co2e.co2e_models import (
    Co2eEstimate,
    Co2eFactor,
    Co2eFactorFile,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.usage import MessageUsage

FACTORS_PATH = Path(__file__).parent / "data" / "co2e_factors.json"

# Cached input tokens skip prefill compute but still cost KV-cache reads.
# Assumption pending measurement; mirrors the ~10x cache price discount.
CACHED_INPUT_ENERGY_FRACTION = 0.1


@cache
def _factor_file() -> Co2eFactorFile:
    return Co2eFactorFile.model_validate(json.loads(FACTORS_PATH.read_text()))


@cache
def _factor_index() -> dict[tuple[str, str, str, str], Co2eFactor]:
    index: dict[tuple[str, str, str, str], Co2eFactor] = {}
    for f in _factor_file().factors:
        name = f.kiln_model_name or f.model
        index[(name, f.provider, f.serving_tier, f.region_mode)] = f
        # Kiln encodes some serving tiers as distinct ModelNames (e.g.
        # glm_5_2_fast). Those rows must also resolve under the default
        # tier, since callers pass the ModelName they actually used.
        if name != f.model:
            index.setdefault((name, f.provider, "standard", f.region_mode), f)
    return index


def _as_str(value: "str | ModelProviderName") -> str:
    if isinstance(value, ModelProviderName):
        return value.value
    return value


def get_co2e_factor(
    model_name: str,
    provider_name: "str | ModelProviderName",
    serving_tier: str = "standard",
    region_mode: str = "default",
) -> Co2eFactor | None:
    return _factor_index().get(
        (_as_str(model_name), _as_str(provider_name), serving_tier, region_mode)
    )


def estimate_co2e(
    model_name: str,
    provider_name: "str | ModelProviderName",
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None = None,
    serving_tier: str = "standard",
    region_mode: str = "default",
) -> Co2eEstimate | None:
    """Estimate grams CO2e and Wh for one request. None if no factor row exists.

    input_tokens is the full prompt count (including any cached portion, as
    providers report it); cached tokens are charged CACHED_INPUT_ENERGY_FRACTION
    of the input factor. Output tokens must include billed reasoning tokens
    (they normally do — providers bill them).
    """
    factor = get_co2e_factor(model_name, provider_name, serving_tier, region_mode)
    if factor is None:
        return None

    in_total = input_tokens or 0
    cached = min(cached_tokens or 0, in_total)
    effective_in = (in_total - cached) + cached * CACHED_INPUT_ENERGY_FRACTION
    out = output_tokens or 0

    g = factor.g_co2e_per_1k_input_tokens.scaled(
        effective_in / 1000.0
    ) + factor.g_co2e_per_1k_output_tokens.scaled(out / 1000.0)
    wh = factor.wh_per_1k_input_tokens.scaled(
        effective_in / 1000.0
    ) + factor.wh_per_1k_output_tokens.scaled(out / 1000.0)

    file = _factor_file()
    return Co2eEstimate(
        g_co2e=g,
        wh=wh,
        basis=factor.basis,
        confidence=factor.confidence,
        methodology_version=file.methodology_version,
        factor_as_of=file.as_of,
        provenance=factor.provenance,
    )


def estimate_co2e_for_usage(
    model_name: str,
    provider_name: "str | ModelProviderName",
    usage: MessageUsage,
    serving_tier: str = "standard",
    region_mode: str = "default",
) -> Co2eEstimate | None:
    return estimate_co2e(
        model_name=model_name,
        provider_name=provider_name,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=usage.cached_tokens,
        serving_tier=serving_tier,
        region_mode=region_mode,
    )
