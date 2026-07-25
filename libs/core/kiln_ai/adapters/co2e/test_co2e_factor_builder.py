import json

from kiln_ai.adapters.co2e.factor_builder import (
    FACTORS_PATH,
    build_factor_file,
)


def _committed():
    return json.loads(FACTORS_PATH.read_text())


def test_committed_factors_match_rebuild():
    """Layer 2 is generated — this fails if someone hand-edits co2e_factors.json
    or edits Layer-1 inputs without rerunning the builder."""
    rebuilt = build_factor_file().model_dump(exclude_none=True)
    assert rebuilt == _committed(), (
        "co2e_factors.json is stale. Regenerate with: "
        "uv run python -m kiln_ai.adapters.co2e.factor_builder"
    )


def _p50(factors, model, provider, tier="standard", region="default"):
    for f in factors:
        if (
            (f.get("kiln_model_name") or f["model"]),
            f["provider"],
            f["serving_tier"],
            f["region_mode"],
        ) == (model, provider, tier, region):
            return f["g_co2e_per_1k_output_tokens"]["p50"]
    raise AssertionError(f"row not found: {model}/{provider}/{tier}/{region}")


def test_sanity_orderings():
    factors = _committed()["factors"]

    # Model-size ladder within one provider.
    haiku = _p50(factors, "claude_4_5_haiku", "anthropic")
    sonnet = _p50(factors, "claude_sonnet_5", "anthropic")
    opus = _p50(factors, "claude_opus_4_8", "anthropic")
    fable = _p50(factors, "claude_fable_5", "anthropic")
    assert haiku < sonnet < opus < fable

    # Fast tier costs more energy than standard.
    assert _p50(factors, "glm_5_2_fast", "fireworks_ai", tier="fast") > _p50(
        factors, "glm_5_2", "fireworks_ai"
    )

    # Clean-grid regions are far below US defaults.
    assert _p50(factors, "gpt_5_6_sol", "azure_openai") > 5 * _p50(
        factors, "gpt_5_6_sol", "azure_openai", region="swedencentral"
    )
    assert _p50(factors, "claude_sonnet_5", "amazon_bedrock") > 4 * _p50(
        factors, "claude_sonnet_5", "amazon_bedrock", region="ca_central_1"
    )

    # Same open model on the Chinese grid is dirtier than on US serving.
    assert _p50(factors, "glm_5_2", "siliconflow_cn") > _p50(
        factors, "glm_5_2", "fireworks_ai"
    )


def test_bands_are_ordered_and_positive():
    for f in _committed()["factors"]:
        for key in (
            "wh_per_1k_output_tokens",
            "wh_per_1k_input_tokens",
            "g_co2e_per_1k_output_tokens",
            "g_co2e_per_1k_input_tokens",
        ):
            band = f[key]
            assert 0 < band["p5"] <= band["p50"] <= band["p95"], (f["model"], key)


def test_optional_columns_behave():
    factors = _committed()["factors"]
    for f in factors:
        # Lifecycle (incl. training) must exceed the operational-only band.
        if "g_co2e_per_1k_output_tokens_incl_training" in f:
            assert (
                f["g_co2e_per_1k_output_tokens_incl_training"]["p50"]
                > f["g_co2e_per_1k_output_tokens"]["p50"]
            )
        # Market-based sits below location-based; only providers with
        # disclosed contractual factors carry it (Google 65, Microsoft 73).
        if "g_co2e_per_1k_output_tokens_market" in f:
            assert f["provider"] in ("gemini_api", "azure_openai", "openai")
            assert (
                f["g_co2e_per_1k_output_tokens_market"]["p50"]
                < f["g_co2e_per_1k_output_tokens"]["p50"]
            )
    # Closed models with no disclosed basis must NOT carry a training column.
    for f in factors:
        if f["model"].startswith(("claude_", "gpt_", "gemini_")):
            assert "g_co2e_per_1k_output_tokens_incl_training" not in f


def test_every_row_has_provenance_and_confidence():
    for f in _committed()["factors"]:
        assert f["confidence"] in ("low", "medium", "medium-high", "high")
        prov = f["provenance"]
        assert prov["model_source"] and prov["provider_source"]
