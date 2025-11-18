import asyncio
import os
from unittest.mock import patch

import pytest
import yaml

from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.utils.config import Config
from kiln_ai.utils.model_rate_limiter import ModelRateLimiter, RateLimits


@pytest.fixture
def temp_home(tmp_path):
    with (
        patch.object(os.path, "expanduser", return_value=str(tmp_path)),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        yield tmp_path


@pytest.fixture
def rate_limits_file(temp_home):
    """Create a rate limits file with test data."""
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    rate_limits = {
        "provider_limits": {},
        "model_limits": {
            "openai": {"gpt_5": 5, "gpt_4o": 3},
            "anthropic": {"claude_opus_4_1": 2},
        },
    }
    with open(rate_limits_path, "w") as f:
        yaml.dump(rate_limits, f)
    return rate_limits


def test_init_with_explicit_limits():
    """Test initialization with explicit rate limits."""
    rate_limits = RateLimits(model_limits={"openai": {"gpt_5": 10}})
    limiter = ModelRateLimiter(rate_limits)
    assert limiter.get_limit("openai", "gpt_5") == 10


def test_init_loads_from_file(rate_limits_file):
    """Test initialization loads rate limits from file."""
    limiter = ModelRateLimiter()
    assert limiter.get_limit("openai", "gpt_5") == 5
    assert limiter.get_limit("anthropic", "claude_opus_4_1") == 2


def test_init_with_no_file(temp_home):
    """Test initialization when no rate limits file exists."""
    limiter = ModelRateLimiter()
    assert limiter.get_limit("openai", "gpt_5") is None


def test_get_limit():
    """Test getting rate limits."""
    rate_limits = RateLimits(model_limits={"openai": {"gpt_5": 10, "gpt_4o": 5}})
    limiter = ModelRateLimiter(rate_limits)

    assert limiter.get_limit("openai", "gpt_5") == 10
    assert limiter.get_limit("openai", "gpt_4o") == 5
    assert limiter.get_limit("openai", "nonexistent") is None
    assert limiter.get_limit("anthropic", "claude") is None


def test_set_limit():
    """Test setting rate limits."""
    limiter = ModelRateLimiter(RateLimits())

    limiter.set_limit("openai", "gpt_5", 10)
    assert limiter.get_limit("openai", "gpt_5") == 10

    limiter.set_limit("openai", "gpt_4o", 5)
    assert limiter.get_limit("openai", "gpt_4o") == 5


def test_set_limit_to_none_removes_limit():
    """Test that setting limit to None removes it."""
    rate_limits = RateLimits(model_limits={"openai": {"gpt_5": 10}})
    limiter = ModelRateLimiter(rate_limits)

    limiter.set_limit("openai", "gpt_5", None)
    assert limiter.get_limit("openai", "gpt_5") is None


def test_set_limit_to_zero_removes_limit():
    """Test that setting limit to 0 removes it."""
    rate_limits = RateLimits(model_limits={"openai": {"gpt_5": 10}})
    limiter = ModelRateLimiter(rate_limits)

    limiter.set_limit("openai", "gpt_5", 0)
    assert limiter.get_limit("openai", "gpt_5") is None


def test_reload(rate_limits_file):
    """Test reloading rate limits from file."""
    limiter = ModelRateLimiter()
    assert limiter.get_limit("openai", "gpt_5") == 5

    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    new_limits = {"model_limits": {"openai": {"gpt_5": 20}}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(new_limits, f)

    limiter.reload()
    assert limiter.get_limit("openai", "gpt_5") == 20
    assert limiter.get_limit("anthropic", "claude_opus_4_1") is None


@pytest.mark.asyncio
async def test_limit_context_manager_unlimited():
    """Test that unlimited models don't block."""
    limiter = ModelRateLimiter(RateLimits())

    results = []

    async def task(i):
        async with limiter.limit("openai", "gpt_5"):
            results.append(f"start-{i}")
            await asyncio.sleep(0.01)
            results.append(f"end-{i}")

    await asyncio.gather(*[task(i) for i in range(5)])

    assert len(results) == 10
    assert results.count("start-0") == 1


@pytest.mark.asyncio
async def test_limit_context_manager_with_limit():
    """Test that rate limiting actually limits concurrency."""
    rate_limits = RateLimits(model_limits={"openai": {"gpt_5": 2}})
    limiter = ModelRateLimiter(rate_limits)

    active_count = 0
    max_concurrent = 0
    results = []

    async def task(i):
        nonlocal active_count, max_concurrent
        async with limiter.limit("openai", "gpt_5"):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            results.append(f"start-{i}")
            await asyncio.sleep(0.05)
            active_count -= 1
            results.append(f"end-{i}")

    await asyncio.gather(*[task(i) for i in range(5)])

    assert max_concurrent == 2
    assert len(results) == 10


@pytest.mark.asyncio
async def test_different_models_independent_limits():
    """Test that different models have independent rate limits."""
    rate_limits = RateLimits(model_limits={"openai": {"gpt_5": 1, "gpt_4o": 1}})
    limiter = ModelRateLimiter(rate_limits)

    gpt5_active = 0
    gpt4o_active = 0
    max_total_concurrent = 0

    async def task_gpt5():
        nonlocal gpt5_active, max_total_concurrent
        async with limiter.limit("openai", "gpt_5"):
            gpt5_active += 1
            max_total_concurrent = max(max_total_concurrent, gpt5_active + gpt4o_active)
            await asyncio.sleep(0.05)
            gpt5_active -= 1

    async def task_gpt4o():
        nonlocal gpt4o_active, max_total_concurrent
        async with limiter.limit("openai", "gpt_4o"):
            gpt4o_active += 1
            max_total_concurrent = max(max_total_concurrent, gpt5_active + gpt4o_active)
            await asyncio.sleep(0.05)
            gpt4o_active -= 1

    await asyncio.gather(task_gpt5(), task_gpt5(), task_gpt4o(), task_gpt4o())

    assert max_total_concurrent == 2


@pytest.mark.asyncio
async def test_limit_enforces_max_concurrent():
    """Test that the semaphore enforces the exact limit."""
    rate_limits = RateLimits(model_limits={"openai": {"gpt_5": 3}})
    limiter = ModelRateLimiter(rate_limits)

    concurrent_count = []

    async def task():
        async with limiter.limit("openai", "gpt_5"):
            semaphore = limiter._get_semaphore("openai", "gpt_5")
            if semaphore:
                concurrent_count.append(3 - semaphore._value)
            await asyncio.sleep(0.02)

    await asyncio.gather(*[task() for i in range(10)])

    assert max(concurrent_count) == 3
    assert min(concurrent_count) >= 1


@pytest.mark.asyncio
async def test_set_limit_updates_semaphore():
    """Test that setting a new limit updates the semaphore."""
    limiter = ModelRateLimiter(RateLimits(model_limits={"openai": {"gpt_5": 10}}))

    limiter.set_limit("openai", "gpt_5", 2)

    active_count = 0
    max_concurrent = 0

    async def task():
        nonlocal active_count, max_concurrent
        async with limiter.limit("openai", "gpt_5"):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1

    await asyncio.gather(*[task() for i in range(5)])

    assert max_concurrent == 2


def test_semaphore_key_generation():
    """Test that semaphore keys are generated correctly."""
    limiter = ModelRateLimiter(RateLimits())

    key1 = limiter._get_semaphore_key("openai", "gpt_5")
    key2 = limiter._get_semaphore_key("anthropic", "claude")
    key3 = limiter._get_semaphore_key("openai", "gpt_5")

    assert key1 == "openai::gpt_5"
    assert key2 == "anthropic::claude"
    assert key1 == key3
    assert key1 != key2


def test_provider_limit_basic():
    """Test basic provider-wide rate limiting."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 10, "anthropic": 5},
            model_limits={},
        )
    )

    assert limiter.get_provider_limit("openai") == 10
    assert limiter.get_provider_limit("anthropic") == 5
    assert limiter.get_provider_limit("nonexistent") is None


def test_provider_limit_fallback():
    """Test that provider limit is used when no model-specific limit exists."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 10},
            model_limits={"openai": {"gpt_5": 5}},
        )
    )

    assert limiter.get_limit("openai", "gpt_5") == 5
    assert limiter.get_limit("openai", "gpt_4o") == 10


def test_model_limit_precedence():
    """Test that model-specific limit takes precedence over provider limit."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 10},
            model_limits={"openai": {"gpt_5": 3}},
        )
    )

    assert limiter.get_limit("openai", "gpt_5") == 3
    assert limiter.get_provider_limit("openai") == 10


def test_unlimited_when_no_limits():
    """Test that None is returned when neither provider nor model limit exists."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 10},
            model_limits={},
        )
    )

    assert limiter.get_limit("anthropic", "claude") is None


def test_set_provider_limit():
    """Test setting provider-wide rate limits."""
    limiter = ModelRateLimiter(RateLimits())

    limiter.set_provider_limit("openai", 15)
    assert limiter.get_provider_limit("openai") == 15

    limiter.set_provider_limit("anthropic", 8)
    assert limiter.get_provider_limit("anthropic") == 8


def test_set_provider_limit_to_none_removes_limit():
    """Test that setting provider limit to None removes it."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 10},
            model_limits={},
        )
    )

    limiter.set_provider_limit("openai", None)
    assert limiter.get_provider_limit("openai") is None


def test_set_provider_limit_to_zero_removes_limit():
    """Test that setting provider limit to 0 removes it."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 10},
            model_limits={},
        )
    )

    limiter.set_provider_limit("openai", 0)
    assert limiter.get_provider_limit("openai") is None


@pytest.mark.asyncio
async def test_provider_limit_enforces_concurrency():
    """Test that provider-wide limit enforces concurrency across models."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 2},
            model_limits={},
        )
    )

    active_count = 0
    max_concurrent = 0

    async def task(model):
        nonlocal active_count, max_concurrent
        async with limiter.limit("openai", model):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1

    await asyncio.gather(
        task("gpt_5"),
        task("gpt_5"),
        task("gpt_4o"),
        task("gpt_4o"),
        task("gpt_3_5"),
    )

    assert max_concurrent == 2


@pytest.mark.asyncio
async def test_model_limit_overrides_provider_limit_concurrency():
    """Test that model-specific limit overrides provider limit for concurrency."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 5},
            model_limits={"openai": {"gpt_5": 1}},
        )
    )

    gpt5_active = 0
    gpt4o_active = 0
    max_gpt5_concurrent = 0
    max_gpt4o_concurrent = 0

    async def task_gpt5():
        nonlocal gpt5_active, max_gpt5_concurrent
        async with limiter.limit("openai", "gpt_5"):
            gpt5_active += 1
            max_gpt5_concurrent = max(max_gpt5_concurrent, gpt5_active)
            await asyncio.sleep(0.05)
            gpt5_active -= 1

    async def task_gpt4o():
        nonlocal gpt4o_active, max_gpt4o_concurrent
        async with limiter.limit("openai", "gpt_4o"):
            gpt4o_active += 1
            max_gpt4o_concurrent = max(max_gpt4o_concurrent, gpt4o_active)
            await asyncio.sleep(0.05)
            gpt4o_active -= 1

    await asyncio.gather(
        task_gpt5(),
        task_gpt5(),
        task_gpt5(),
        task_gpt4o(),
        task_gpt4o(),
        task_gpt4o(),
    )

    assert max_gpt5_concurrent == 1
    assert max_gpt4o_concurrent == 3


def test_pydantic_model_initialization():
    """Test that RateLimits Pydantic model works correctly."""
    rate_limits = RateLimits(
        provider_limits={},
        model_limits={
            "openai": {"gpt_5": 10, "gpt_4o": 5},
            "anthropic": {"claude_opus_4_1": 2},
        },
    )
    limiter = ModelRateLimiter(rate_limits)

    assert limiter.get_limit("openai", "gpt_5") == 10
    assert limiter.get_limit("openai", "gpt_4o") == 5
    assert limiter.get_limit("anthropic", "claude_opus_4_1") == 2
    assert limiter.get_provider_limit("openai") is None


def test_new_format_with_both_limits():
    """Test new format with both provider and model limits."""
    limiter = ModelRateLimiter(
        RateLimits(
            provider_limits={"openai": 20, "anthropic": 10},
            model_limits={
                "openai": {"gpt_5": 5},
                "anthropic": {"claude_opus_4_1": 3},
            },
        )
    )

    assert limiter.get_provider_limit("openai") == 20
    assert limiter.get_provider_limit("anthropic") == 10
    assert limiter.get_limit("openai", "gpt_5") == 5
    assert limiter.get_limit("openai", "gpt_4o") == 20
    assert limiter.get_limit("anthropic", "claude_opus_4_1") == 3


def test_empty_rate_limits():
    """Test initialization with empty rate limits."""
    limiter = ModelRateLimiter(RateLimits())

    assert limiter.get_limit("openai", "gpt_5") is None
    assert limiter.get_provider_limit("openai") is None


@pytest.fixture
def new_format_rate_limits_file(temp_home):
    """Create a rate limits file with new format."""
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    rate_limits = {
        "provider_limits": {"openai": 20, "anthropic": 10},
        "model_limits": {
            "openai": {"gpt_5": 5},
            "anthropic": {"claude_opus_4_1": 3},
        },
    }
    with open(rate_limits_path, "w") as f:
        yaml.dump(rate_limits, f)
    return rate_limits


def test_reload_new_format(new_format_rate_limits_file):
    """Test reloading rate limits from file with new format."""
    limiter = ModelRateLimiter()
    assert limiter.get_provider_limit("openai") == 20
    assert limiter.get_limit("openai", "gpt_5") == 5

    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    new_limits = {
        "provider_limits": {"openai": 50},
        "model_limits": {"openai": {"gpt_5": 10}},
    }
    with open(rate_limits_path, "w") as f:
        yaml.dump(new_limits, f)

    limiter.reload()
    assert limiter.get_provider_limit("openai") == 50
    assert limiter.get_limit("openai", "gpt_5") == 10
    assert limiter.get_provider_limit("anthropic") is None


def test_get_model_specified_max_concurrent_requests_with_model_property():
    """Test that model-specific max_parallel_requests is returned when set."""
    from unittest.mock import MagicMock

    limiter = ModelRateLimiter(RateLimits())

    # Create mock model providers with specific max_parallel_requests
    mock_provider_2 = MagicMock()
    mock_provider_2.max_parallel_requests = 2

    mock_provider_1 = MagicMock()
    mock_provider_1.max_parallel_requests = 1

    with patch(
        "kiln_ai.adapters.ml_model_list.built_in_models_from_provider"
    ) as mock_built_in:
        # Test model with max_parallel_requests=2
        mock_built_in.return_value = mock_provider_2
        assert (
            limiter.get_model_specified_max_concurrent_requests(
                "openai", "test_model_2"
            )
            == 2
        )

        # Test model with max_parallel_requests=1
        mock_built_in.return_value = mock_provider_1
        assert (
            limiter.get_model_specified_max_concurrent_requests(
                ModelProviderName.ollama, "test_model_1"
            )
            == 1
        )


def test_get_model_specified_max_concurrent_requests_default():
    """Test that default limit is returned when model doesn't specify max_parallel_requests."""
    limiter = ModelRateLimiter(RateLimits(), default_provider_limit=10)

    # Most models don't have max_parallel_requests set, so should use default
    assert limiter.get_model_specified_max_concurrent_requests("openai", "gpt_4") == 10
    assert (
        limiter.get_model_specified_max_concurrent_requests(
            "anthropic", "claude_opus_4"
        )
        == 10
    )


def test_get_model_specified_max_concurrent_requests_ollama_default():
    """Test that Ollama provider defaults to 1 concurrent request."""
    limiter = ModelRateLimiter(RateLimits())

    # Ollama should default to 1
    assert (
        limiter.get_model_specified_max_concurrent_requests(
            ModelProviderName.ollama, "llama2"
        )
        == 1
    )


def test_get_model_specified_max_concurrent_requests_unknown_model():
    """Test that unknown models use provider default."""
    limiter = ModelRateLimiter(RateLimits(), default_provider_limit=10)

    # Unknown model should use provider default
    assert (
        limiter.get_model_specified_max_concurrent_requests(
            "openai", "nonexistent_model"
        )
        == 10
    )


@pytest.mark.asyncio
async def test_default_semaphore_limits_concurrency():
    """Test that default semaphore actually limits concurrency when no explicit limit is set."""
    limiter = ModelRateLimiter(RateLimits(), default_provider_limit=10)

    active_count = 0
    max_concurrent = 0

    async def task():
        nonlocal active_count, max_concurrent
        async with limiter.limit("openai", "gpt_4"):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.02)
            active_count -= 1

    # Run more tasks than default limit
    await asyncio.gather(*[task() for _ in range(20)])

    # Should be limited to DEFAULT_PROVIDER_LIMIT (10)
    assert max_concurrent == 10


@pytest.mark.asyncio
async def test_default_semaphore_ollama_limits_to_one():
    """Test that Ollama defaults to 1 concurrent request when no explicit limit is set."""
    limiter = ModelRateLimiter(RateLimits())

    active_count = 0
    max_concurrent = 0

    async def task():
        nonlocal active_count, max_concurrent
        async with limiter.limit(ModelProviderName.ollama, "llama2"):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.02)
            active_count -= 1

    # Run multiple tasks
    await asyncio.gather(*[task() for _ in range(5)])

    # Should be limited to 1 for Ollama
    assert max_concurrent == 1


@pytest.mark.asyncio
async def test_default_semaphore_respects_model_max_parallel_requests():
    """Test that default semaphore uses model's max_parallel_requests when set."""
    from unittest.mock import MagicMock

    limiter = ModelRateLimiter(RateLimits())

    # Create mock model provider with max_parallel_requests=2
    mock_provider = MagicMock()
    mock_provider.max_parallel_requests = 2

    active_count = 0
    max_concurrent = 0

    async def task():
        nonlocal active_count, max_concurrent
        async with limiter.limit("openai", "test_model"):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.02)
            active_count -= 1

    with patch(
        "kiln_ai.adapters.ml_model_list.built_in_models_from_provider",
        return_value=mock_provider,
    ):
        # Run multiple tasks - test_model has max_parallel_requests=2
        await asyncio.gather(*[task() for _ in range(5)])

    # Should be limited to 2 (test_model's max_parallel_requests)
    assert max_concurrent == 2


@pytest.mark.asyncio
async def test_explicit_limit_overrides_default():
    """Test that explicitly set rate limits override default behavior."""
    limiter = ModelRateLimiter(RateLimits(model_limits={"openai": {"gpt_4": 3}}))

    active_count = 0
    max_concurrent = 0

    async def task():
        nonlocal active_count, max_concurrent
        async with limiter.limit("openai", "gpt_4"):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.02)
            active_count -= 1

    # Run more tasks than explicit limit
    await asyncio.gather(*[task() for _ in range(10)])

    # Should be limited to explicit limit (3), not default (10)
    assert max_concurrent == 3


@pytest.mark.asyncio
async def test_provider_limit_overrides_default():
    """Test that provider-wide limits override default behavior."""
    limiter = ModelRateLimiter(RateLimits(provider_limits={"openai": 5}))

    active_count = 0
    max_concurrent = 0

    async def task():
        nonlocal active_count, max_concurrent
        async with limiter.limit("openai", "gpt_4"):
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.02)
            active_count -= 1

    # Run more tasks than provider limit
    await asyncio.gather(*[task() for _ in range(15)])

    # Should be limited to provider limit (5), not default (10)
    assert max_concurrent == 5
