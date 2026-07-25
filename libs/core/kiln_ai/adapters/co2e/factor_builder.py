"""Build the committed CO2e factor table (data/co2e_factors.json) from the
provenance-labeled Layer-1 inputs in data/.

Layer-2 (co2e_factors.json) is GENERATED — never hand-edit it. Edit the
Layer-1 JSONs and rerun:

    uv run python -m kiln_ai.adapters.co2e.factor_builder

The build is deterministic (fixed seed, fixed iteration order), so
test_co2e_factor_builder.py can assert the committed file matches a rebuild.

Formula chain (documented in the research repo, experiments/co2e):
    e_out   = 2 * N_active * eta * k_moe * k_quant * u_fleet   [J/output token]
    E_total = E_acc * f_host * f_idle * PUE * tier_mult
    gCO2e   = E_total_kWh * (CI_region + EF_embodied)
"""

import json
import random
from pathlib import Path
from typing import Any

from kiln_ai.adapters.co2e.co2e_models import (
    Co2eFactor,
    Co2eFactorFile,
    Co2eProvenance,
    PercentileBand,
)
from kiln_ai.adapters.co2e.mc import (
    Sampler,
    make_categorical,
    make_sampler,
    percentiles,
    round_sig,
)

DATA_DIR = Path(__file__).parent / "data"
FACTORS_PATH = DATA_DIR / "co2e_factors.json"

N_SAMPLES = 20_000
SEED = 42

_CONFIDENCE_RANK = {
    "disclosed": 3,
    "measured": 3,
    "derived": 2,
    "estimate": 2,
    "inference": 1,
    "speculation": 0,
}
_PROVIDER_RANK = {"medium-high": 3, "medium": 2, "low": 1}
_CONFIDENCE_NAME = {0: "low", 1: "low", 2: "medium", 3: "medium-high"}


def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text())


def _row_confidence(model_label: str, provider_confidence: str) -> str:
    model_score = _CONFIDENCE_RANK.get(model_label, 0)
    prov_score = _PROVIDER_RANK.get(provider_confidence, 1)
    return _CONFIDENCE_NAME[min(model_score, prov_score)]


def _band(values: list[float]) -> PercentileBand:
    return PercentileBand(**round_sig(percentiles(values)))


def build_factor_row(
    row: dict[str, Any],
    models: dict[str, Any],
    providers: dict[str, Any],
    hw_classes: dict[str, Any],
    regions: dict[str, Any],
    consts: dict[str, Any],
    training: dict[str, Any],
    rng: random.Random,
) -> Co2eFactor:
    model = models["models"][row["model"]]
    provider = providers["providers"][row["provider"]]
    tier = row.get("tier", "standard")
    region_mode = row.get("region_mode", "default")

    region_mix = (
        provider["region_mix"]
        if region_mode == "default"
        else provider["region_variants"][region_mode]
    )

    s_active = make_sampler(model["active_b"], rng)
    s_pue = make_sampler(provider["pue"], rng)
    s_rho = make_sampler(consts["rho_in"], rng)
    s_kmoe: Sampler = (
        make_sampler(consts["k_moe"], rng) if model["arch"] == "moe" else (lambda: 1.0)
    )
    s_kquant = make_sampler(consts["k_quant"], rng)
    s_fhost = make_sampler(consts["f_host"], rng)
    s_fidle = make_sampler(consts["f_idle"], rng)
    s_efemb = make_sampler(consts["ef_embodied_g_per_kwh"], rng)
    s_ufleet = make_sampler(consts["u_fleet"], rng)

    sram = "sram_speed_premium" in provider
    if sram:
        s_eta = make_sampler(
            hw_classes["classes"]["gpu_blackwell"]["eta_pj_per_flop"], rng
        )
        s_premium = make_sampler(provider["sram_speed_premium"], rng)
    else:
        s_eta = make_categorical(
            [
                (w, make_sampler(hw_classes["classes"][cid]["eta_pj_per_flop"], rng))
                for cid, w in provider["hardware_mix"].items()
            ],
            rng,
        )
        s_premium = lambda: 1.0  # noqa: E731

    s_tier = make_sampler(
        provider.get("tier_multipliers", {}).get(tier, [1.0, 1.0, 1.0]), rng
    )
    s_ci = make_categorical(
        [
            (w, make_sampler(regions["regions"][rid]["ci"], rng))
            for rid, w in region_mix.items()
        ],
        rng,
    )
    market_ci: float | None = None
    if all("ci_market" in regions["regions"][rid] for rid in region_mix):
        market_ci = sum(
            w * regions["regions"][rid]["ci_market"] for rid, w in region_mix.items()
        )

    train = training["models"].get(row["model"])
    s_train: Sampler | None = None
    if train is not None:
        lifetime_triple = (
            train.get("lifetime_output_tokens_T")
            or training["lifetime_output_tokens_T"][train["volume_tier"]]
        )
        s_tco2e = make_sampler(train["train_tco2e"], rng)
        s_lifetime = make_sampler(lifetime_triple, rng)
        # g per 1k output tokens = (tCO2e * 1e6 g/t) / (T-tokens * 1e12 / 1e3)
        s_train = lambda: s_tco2e() * 1e6 / (s_lifetime() * 1e9)  # noqa: E731

    wh_out: list[float] = []
    wh_in: list[float] = []
    g_out: list[float] = []
    g_in: list[float] = []
    g_market: list[float] = []
    g_lifecycle: list[float] = []
    for _ in range(N_SAMPLES):
        n_active = s_active() * 1e9
        # u_fleet converts batched-benchmark eta to fleet-median reality; the
        # sram speed premium already embodies utilization, so skip it there.
        u_fleet = 1.0 if sram else s_ufleet()
        e_out_j = (
            2.0
            * n_active
            * s_eta()
            * 1e-12
            * s_kmoe()
            * s_kquant()
            * s_premium()
            * u_fleet
        )

        overhead = s_fhost() * s_fidle() * s_pue() * s_tier()
        wh_1k_out = 1000.0 * e_out_j / 3600.0 * overhead
        wh_1k_in = wh_1k_out / s_rho()

        ef_emb = s_efemb()
        ci = s_ci() + ef_emb
        wh_out.append(wh_1k_out)
        wh_in.append(wh_1k_in)
        g_out.append(wh_1k_out / 1000.0 * ci)
        g_in.append(wh_1k_in / 1000.0 * ci)
        if market_ci is not None:
            g_market.append(wh_1k_out / 1000.0 * (market_ci + ef_emb))
        if s_train is not None:
            g_lifecycle.append(g_out[-1] + s_train())

    return Co2eFactor(
        model=row["model"],
        kiln_model_name=row.get("kiln_model_name_override") or model["kiln_model_name"],
        provider=row["provider"],
        serving_tier=tier,
        region_mode=region_mode,
        wh_per_1k_output_tokens=_band(wh_out),
        wh_per_1k_input_tokens=_band(wh_in),
        g_co2e_per_1k_output_tokens=_band(g_out),
        g_co2e_per_1k_input_tokens=_band(g_in),
        g_co2e_per_1k_output_tokens_market=_band(g_market) if g_market else None,
        market_note=(
            "provider-disclosed contractual factors; non-claimant market-based would use residual mix (higher)"
            if g_market
            else None
        ),
        g_co2e_per_1k_output_tokens_incl_training=_band(g_lifecycle)
        if g_lifecycle
        else None,
        training_provenance=(
            {"label": train["label"], "source": train["source"]} if train else None
        ),
        basis="modeled",
        confidence=_row_confidence(model["label"], provider.get("confidence", "low")),  # type: ignore[arg-type]
        provenance=Co2eProvenance(
            model_params=model["label"],
            provider_profile=provider["label"],
            model_source=model["source"],
            provider_source=provider["source"],
        ),
    )


def build_factor_file() -> Co2eFactorFile:
    rng = random.Random(SEED)
    models = _load("model_architectures.json")
    providers = _load("provider_profiles.json")
    hw_classes = _load("hardware_classes.json")
    regions = _load("grid_regions.json")
    consts = _load("constants.json")
    training = _load("training_footprints.json")
    seed_rows = _load("seed_rows.json")

    factors = [
        build_factor_row(
            row, models, providers, hw_classes, regions, consts, training, rng
        )
        for row in seed_rows["rows"]
    ]
    return Co2eFactorFile(
        methodology_version=consts["methodology_version"],
        as_of=consts["as_of"],
        generator=f"kiln_ai.adapters.co2e.factor_builder (Monte Carlo, N={N_SAMPLES}, seed={SEED})",
        accounting={
            "frame": "attributional LCA",
            "functional_unit": "1000 tokens (SCI-for-AI consumer unit, scaled)",
            "boundary": "serving operational (accelerator+host+idle+PUE, fleet-median) + embodied serving hardware; location-based CI",
            "excluded": "training (separate optional incl_training band), networking, end-user devices, end-of-life, water",
        },
        units={
            "wh_per_1k_*": "watt-hours per 1000 tokens, full datacenter boundary",
            "g_co2e_per_1k_*": "grams CO2e per 1000 tokens, location-based grid CI + embodied hardware",
        },
        notes=[
            "Factors are per billed/visible token; hidden unbilled reasoning tokens need a separate multiplier at estimate time.",
            "Never display p50 without the p5-p95 band.",
            "incl_training amortizes provider-boundary training emissions over speculative lifetime volumes - wide bands by construction.",
        ],
        factors=factors,
    )


def write_factor_file() -> None:
    factor_file = build_factor_file()
    FACTORS_PATH.write_text(
        json.dumps(factor_file.model_dump(exclude_none=True), indent=2) + "\n"
    )


if __name__ == "__main__":
    write_factor_file()
    print(f"Wrote {FACTORS_PATH}")
