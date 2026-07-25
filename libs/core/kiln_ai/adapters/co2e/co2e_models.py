from typing import Literal

from pydantic import BaseModel, Field

Co2eBasis = Literal["modeled", "measured", "hybrid"]
Co2eConfidence = Literal["low", "medium", "medium-high", "high"]


class PercentileBand(BaseModel):
    """A P5/P50/P95 uncertainty band. Never display p50 without the band."""

    p5: float = Field(ge=0)
    p50: float = Field(ge=0)
    p95: float = Field(ge=0)

    def scaled(self, factor: float) -> "PercentileBand":
        return PercentileBand(
            p5=self.p5 * factor, p50=self.p50 * factor, p95=self.p95 * factor
        )

    def __add__(self, other: "PercentileBand") -> "PercentileBand":
        # Quantile addition is exact for perfectly correlated distributions.
        # Our input and output factors share every sampled input (same row),
        # so their correlation is near 1 and this is a close approximation.
        return PercentileBand(
            p5=self.p5 + other.p5, p50=self.p50 + other.p50, p95=self.p95 + other.p95
        )


class Co2eProvenance(BaseModel):
    model_params: str
    provider_profile: str
    model_source: str
    provider_source: str


class Co2eFactor(BaseModel):
    """One materialized factor row: (model, provider, serving tier, region mode).

    Accounting frame (see docs/co2e_methodology.md): attributional LCA,
    functional unit = 1000 tokens, serving operational energy + embodied
    serving hardware, location-based grid carbon intensity. Training is a
    separate provider-boundary metric surfaced only in the optional
    incl_training band. Factors are per billed/visible token.
    """

    model: str
    kiln_model_name: str | None = None
    provider: str
    serving_tier: str = "standard"
    region_mode: str = "default"
    wh_per_1k_output_tokens: PercentileBand
    wh_per_1k_input_tokens: PercentileBand
    g_co2e_per_1k_output_tokens: PercentileBand
    g_co2e_per_1k_input_tokens: PercentileBand
    g_co2e_per_1k_output_tokens_market: PercentileBand | None = None
    market_note: str | None = None
    g_co2e_per_1k_output_tokens_incl_training: PercentileBand | None = None
    training_provenance: dict[str, str] | None = None
    basis: Co2eBasis = "modeled"
    confidence: Co2eConfidence
    provenance: Co2eProvenance


class Co2eFactorFile(BaseModel):
    methodology_version: str
    as_of: str
    generator: str
    accounting: dict[str, str]
    units: dict[str, str]
    notes: list[str]
    factors: list[Co2eFactor]


class Co2eEstimate(BaseModel):
    """Estimated footprint for one request/run. All bands are totals (grams / Wh)."""

    g_co2e: PercentileBand
    wh: PercentileBand
    basis: Co2eBasis
    confidence: Co2eConfidence
    methodology_version: str
    factor_as_of: str
    provenance: Co2eProvenance
