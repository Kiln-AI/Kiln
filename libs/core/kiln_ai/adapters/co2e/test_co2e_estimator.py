import pytest

from kiln_ai.adapters.co2e import (
    Co2eEstimate,
    estimate_co2e,
    estimate_co2e_for_usage,
    get_co2e_factor,
)
from kiln_ai.adapters.co2e.estimator import CACHED_INPUT_ENERGY_FRACTION
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.usage import MessageUsage


def test_lookup_hit_has_ordered_bands():
    factor = get_co2e_factor("glm_5_2", "fireworks_ai")
    assert factor is not None
    for band in (
        factor.g_co2e_per_1k_output_tokens,
        factor.g_co2e_per_1k_input_tokens,
        factor.wh_per_1k_output_tokens,
        factor.wh_per_1k_input_tokens,
    ):
        assert band.p5 <= band.p50 <= band.p95


def test_lookup_accepts_provider_enum():
    assert get_co2e_factor("glm_5_2", ModelProviderName.fireworks_ai) is not None


def test_lookup_miss_returns_none():
    assert get_co2e_factor("glm_5_2", "openai") is None
    assert get_co2e_factor("not_a_model", "fireworks_ai") is None
    assert get_co2e_factor("glm_5_2", "fireworks_ai", region_mode="mars") is None


def test_tier_encoded_model_name_resolves_with_default_tier():
    # Kiln models the Fireworks fast tier as its own ModelName; the natural
    # call passes serving_tier="standard" and must still resolve.
    fast = get_co2e_factor("glm_5_2_fast", "fireworks_ai")
    std = get_co2e_factor("glm_5_2", "fireworks_ai")
    assert fast is not None and std is not None
    assert fast.serving_tier == "fast"
    assert fast.g_co2e_per_1k_output_tokens.p50 > std.g_co2e_per_1k_output_tokens.p50


def test_estimate_sums_input_and_output_components():
    factor = get_co2e_factor("claude_sonnet_5", "anthropic")
    assert factor is not None
    estimate = estimate_co2e(
        "claude_sonnet_5", "anthropic", input_tokens=1000, output_tokens=1000
    )
    assert isinstance(estimate, Co2eEstimate)
    expected_p50 = (
        factor.g_co2e_per_1k_input_tokens.p50 + factor.g_co2e_per_1k_output_tokens.p50
    )
    assert estimate.g_co2e.p50 == pytest.approx(expected_p50)
    assert estimate.g_co2e.p5 <= estimate.g_co2e.p50 <= estimate.g_co2e.p95
    assert estimate.wh.p50 > 0
    assert estimate.methodology_version
    assert estimate.factor_as_of


def test_estimate_scales_linearly_with_tokens():
    small = estimate_co2e(
        "glm_5_2", "fireworks_ai", input_tokens=500, output_tokens=250
    )
    large = estimate_co2e(
        "glm_5_2", "fireworks_ai", input_tokens=5000, output_tokens=2500
    )
    assert small is not None and large is not None
    assert large.g_co2e.p50 == pytest.approx(small.g_co2e.p50 * 10)


def test_cached_tokens_are_discounted():
    uncached = estimate_co2e(
        "glm_5_2", "fireworks_ai", input_tokens=10_000, output_tokens=0
    )
    cached = estimate_co2e(
        "glm_5_2",
        "fireworks_ai",
        input_tokens=10_000,
        output_tokens=0,
        cached_tokens=10_000,
    )
    assert uncached is not None and cached is not None
    assert cached.g_co2e.p50 == pytest.approx(
        uncached.g_co2e.p50 * CACHED_INPUT_ENERGY_FRACTION
    )


def test_cached_tokens_capped_at_input_tokens():
    over = estimate_co2e(
        "glm_5_2",
        "fireworks_ai",
        input_tokens=1000,
        output_tokens=0,
        cached_tokens=99_999,
    )
    exact = estimate_co2e(
        "glm_5_2",
        "fireworks_ai",
        input_tokens=1000,
        output_tokens=0,
        cached_tokens=1000,
    )
    assert over is not None and exact is not None
    assert over.g_co2e.p50 == pytest.approx(exact.g_co2e.p50)


def test_estimate_handles_none_token_counts():
    estimate = estimate_co2e(
        "glm_5_2", "fireworks_ai", input_tokens=None, output_tokens=None
    )
    assert estimate is not None
    assert estimate.g_co2e.p50 == 0.0


def test_estimate_for_usage():
    usage = MessageUsage(input_tokens=2000, output_tokens=500, cached_tokens=1000)
    via_usage = estimate_co2e_for_usage("claude_sonnet_5", "anthropic", usage)
    direct = estimate_co2e(
        "claude_sonnet_5",
        "anthropic",
        input_tokens=2000,
        output_tokens=500,
        cached_tokens=1000,
    )
    assert via_usage is not None and direct is not None
    assert via_usage.g_co2e.p50 == pytest.approx(direct.g_co2e.p50)


def test_estimate_miss_returns_none():
    assert estimate_co2e("not_a_model", "openai", 100, 100) is None


def test_region_variant_rows_resolve():
    default = get_co2e_factor("claude_sonnet_5", "amazon_bedrock")
    montreal = get_co2e_factor(
        "claude_sonnet_5", "amazon_bedrock", region_mode="ca_central_1"
    )
    assert default is not None and montreal is not None
    assert (
        montreal.g_co2e_per_1k_output_tokens.p50
        < default.g_co2e_per_1k_output_tokens.p50
    )
