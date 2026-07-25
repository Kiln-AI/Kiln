"""CO2e estimation for LLM inference.

A provenance-first factor table (grams CO2e and Wh per 1k tokens, P5/P50/P95)
keyed by Kiln's (ModelName, ModelProviderName) plus serving tier and region
mode, with a deterministic builder from labeled Layer-1 inputs.

Accounting frame: attributional LCA; functional unit 1000 tokens; serving
operational energy + embodied serving hardware; location-based carbon
intensity primary. Training is a separate provider-boundary metric surfaced
only in the optional incl_training band. Research and methodology live in the
experiments repo (experiments/co2e).
"""

from kiln_ai.adapters.co2e.co2e_models import (
    Co2eEstimate,
    Co2eFactor,
    Co2eFactorFile,
    Co2eProvenance,
    PercentileBand,
)
from kiln_ai.adapters.co2e.estimator import (
    estimate_co2e,
    estimate_co2e_for_usage,
    get_co2e_factor,
)

__all__ = [
    "Co2eEstimate",
    "Co2eFactor",
    "Co2eFactorFile",
    "Co2eProvenance",
    "PercentileBand",
    "estimate_co2e",
    "estimate_co2e_for_usage",
    "get_co2e_factor",
]
