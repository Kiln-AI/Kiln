import asyncio
import os
from unittest.mock import patch

import pytest
import yaml

from kiln_ai.utils.config import Config
from kiln_ai.utils.model_rate_limiter import ModelRateLimiter


@pytest.fixture
def temp_home(tmp_path):
    with patch.object(os.path, "expanduser", return_value=str(tmp_path)):
        yield tmp_path


@pytest.fixture
def rate_limits_file(temp_home):
    """Create a rate limits file with test data."""
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    rate_limits = {
        "openai": {"gpt_5": 5, "gpt_4o": 3},
        "anthropic": {"claude_opus_4_1": 2},
    }
    with open(rate_limits_path, "w") as f:
        yaml.dump(rate_limits, f)
    return rate_limits


def test_init_with_explicit_limits():
    """Test initialization with explicit rate limits."""
    rate_limits = {"openai": {"gpt_5": 10}}
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
    rate_limits = {"openai": {"gpt_5": 10, "gpt_4o": 5}}
    limiter = ModelRateLimiter(rate_limits)

    assert limiter.get_limit("openai", "gpt_5") == 10
    assert limiter.get_limit("openai", "gpt_4o") == 5
    assert limiter.get_limit("openai", "nonexistent") is None
    assert limiter.get_limit("anthropic", "claude") is None


def test_set_limit():
    """Test setting rate limits."""
    limiter = ModelRateLimiter({})

    limiter.set_limit("openai", "gpt_5", 10)
    assert limiter.get_limit("openai", "gpt_5") == 10

    limiter.set_limit("openai", "gpt_4o", 5)
    assert limiter.get_limit("openai", "gpt_4o") == 5


def test_set_limit_to_none_removes_limit():
    """Test that setting limit to None removes it."""
    rate_limits = {"openai": {"gpt_5": 10}}
    limiter = ModelRateLimiter(rate_limits)

    limiter.set_limit("openai", "gpt_5", None)
    assert limiter.get_limit("openai", "gpt_5") is None


def test_set_limit_to_zero_removes_limit():
    """Test that setting limit to 0 removes it."""
    rate_limits = {"openai": {"gpt_5": 10}}
    limiter = ModelRateLimiter(rate_limits)

    limiter.set_limit("openai", "gpt_5", 0)
    assert limiter.get_limit("openai", "gpt_5") is None


def test_reload(rate_limits_file):
    """Test reloading rate limits from file."""
    limiter = ModelRateLimiter()
    assert limiter.get_limit("openai", "gpt_5") == 5

    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    new_limits = {"openai": {"gpt_5": 20}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(new_limits, f)

    limiter.reload()
    assert limiter.get_limit("openai", "gpt_5") == 20
    assert limiter.get_limit("anthropic", "claude_opus_4_1") is None


@pytest.mark.asyncio
async def test_limit_context_manager_unlimited():
    """Test that unlimited models don't block."""
    limiter = ModelRateLimiter({})

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
    rate_limits = {"openai": {"gpt_5": 2}}
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
    rate_limits = {"openai": {"gpt_5": 1, "gpt_4o": 1}}
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
    rate_limits = {"openai": {"gpt_5": 3}}
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
    limiter = ModelRateLimiter({"openai": {"gpt_5": 10}})

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
    limiter = ModelRateLimiter({})

    key1 = limiter._get_semaphore_key("openai", "gpt_5")
    key2 = limiter._get_semaphore_key("anthropic", "claude")
    key3 = limiter._get_semaphore_key("openai", "gpt_5")

    assert key1 == "openai::gpt_5"
    assert key2 == "anthropic::claude"
    assert key1 == key3
    assert key1 != key2
