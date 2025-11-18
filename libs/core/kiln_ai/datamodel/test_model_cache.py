from pathlib import Path
from unittest import mock

import pytest
from pydantic import BaseModel

from kiln_ai.datamodel.basemodel import KilnBaseModel
from kiln_ai.datamodel.model_cache import ModelCache


# Define a simple Pydantic model for testing
class ModelTest(BaseModel):
    name: str
    value: int


# Define a test model that inherits from KilnBaseModel for readonly testing
class KilnModelTest(KilnBaseModel):
    name: str
    value: int


@pytest.fixture
def model_cache():
    return ModelCache()


def should_skip_test(model_cache):
    return not model_cache._enabled


@pytest.fixture
def test_path(tmp_path):
    # Create a temporary file path for testing
    test_file = tmp_path / "test_model.kiln"
    test_file.touch()  # Create the file
    return test_file


def test_set_and_get_model(model_cache, test_path):
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime_ns = test_path.stat().st_mtime_ns

    model_cache.set_model(test_path, model, mtime_ns)
    cached_model = model_cache.get_model(test_path, KilnModelTest)

    assert cached_model is not None
    assert cached_model.name == "test"
    assert cached_model.value == 123


def test_invalidate_model(model_cache, test_path):
    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime = test_path.stat().st_mtime

    model_cache.set_model(test_path, model, mtime)
    model_cache.invalidate(test_path)
    cached_model = model_cache.get_model(test_path, KilnModelTest)

    assert cached_model is None


def test_clear_cache(model_cache, test_path):
    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime = test_path.stat().st_mtime

    model_cache.set_model(test_path, model, mtime)
    model_cache.clear()
    cached_model = model_cache.get_model(test_path, KilnModelTest)

    assert cached_model is None


def test_cache_invalid_due_to_mtime_change(model_cache, test_path):
    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime = test_path.stat().st_mtime

    model_cache.set_model(test_path, model, mtime)

    # Simulate a file modification by updating the mtime
    test_path.touch()
    cached_model = model_cache.get_model(test_path, KilnModelTest)

    assert cached_model is None


def test_get_model_wrong_type(model_cache, test_path):
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    class AnotherModel(KilnBaseModel):
        other_field: str

    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime_ns = test_path.stat().st_mtime_ns

    model_cache.set_model(test_path, model, mtime_ns)

    with pytest.raises(ValueError):
        model_cache.get_model(test_path, AnotherModel)

    # Test that the cache invalidates
    cached_model = model_cache.get_model(test_path, KilnModelTest)
    assert cached_model is None


def test_is_cache_valid_true(model_cache, test_path):
    mtime_ns = test_path.stat().st_mtime_ns
    assert model_cache._is_cache_valid(test_path, mtime_ns) is True


def test_is_cache_valid_false_due_to_mtime_change(model_cache, test_path):
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    mtime_ns = test_path.stat().st_mtime_ns
    # Simulate a file modification by updating the mtime
    test_path.touch()
    assert model_cache._is_cache_valid(test_path, mtime_ns) is False


def test_is_cache_valid_false_due_to_missing_file(model_cache):
    non_existent_path = Path("/non/existent/path")
    assert model_cache._is_cache_valid(non_existent_path, 0) is False


def test_benchmark_get_model(benchmark, model_cache, test_path):
    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime = test_path.stat().st_mtime

    # Set the model in the cache
    model_cache.set_model(test_path, model, mtime)

    # Benchmark the get_model method
    def get_model():
        return model_cache.get_model(test_path, KilnModelTest)

    benchmark(get_model)
    stats = benchmark.stats.stats

    # 25k ops per second is the target. Getting 250k on Macbook, but CI will be slower
    target = 1 / 25000
    if stats.mean > target:
        pytest.fail(
            f"Average time per iteration: {stats.mean}, expected less than {target}"
        )


def test_get_model_returns_copy(model_cache, test_path):
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime_ns = test_path.stat().st_mtime_ns

    # Set the model in the cache
    model_cache.set_model(test_path, model, mtime_ns)

    # Get a copy of the model from the cache (readonly should be the same instance)
    readonly_cached_model = model_cache.get_model(
        test_path, KilnModelTest, readonly=True
    )
    assert model == readonly_cached_model

    # Get a copy of the model from the cache (mutable should be a different instance, but same data)
    cached_model = model_cache.get_model(test_path, KilnModelTest, readonly=False)
    assert cached_model is not model
    assert cached_model.name == model.name
    assert cached_model.value == model.value
    assert cached_model._readonly is False  # Copy should be mutable
    assert model._readonly is True  # Original should be readonly

    # Mutate the cached model
    cached_model.name = "mutated"

    # Get the model again from the cache
    new_cached_model = model_cache.get_model(test_path, KilnModelTest)

    # Assert that the new cached model has the original values
    assert new_cached_model.name == model.name == "test"
    assert new_cached_model.value == model.value

    # Save the mutated model back to the cache (not a normal flow)
    cached_model.mark_as_readonly()  # Mark as readonly before caching
    model_cache.set_model(test_path, cached_model, mtime_ns)

    # Get the model again from the cache
    updated_cached_model = model_cache.get_model(test_path, KilnModelTest)

    # Assert that the updated cached model has the mutated values
    assert updated_cached_model.name == "mutated"
    assert updated_cached_model.value == 123


def test_no_cache_when_no_fine_granularity(model_cache, test_path):
    model = ModelTest(name="test", value=123)
    mtime_ns = test_path.stat().st_mtime_ns

    model_cache._enabled = False
    model_cache.set_model(test_path, model, mtime_ns)
    cached_model = model_cache.get_model(test_path, ModelTest)

    # Assert that the model is not cached
    assert cached_model is None
    assert model_cache.model_cache == {}
    assert model_cache._enabled is False


def test_check_timestamp_granularity_macos():
    with mock.patch("sys.platform", "darwin"):
        cache = ModelCache()
        assert cache._check_timestamp_granularity() is True
        assert cache._enabled is True


def test_check_timestamp_granularity_windows():
    with mock.patch("sys.platform", "win32"):
        cache = ModelCache()
        assert cache._check_timestamp_granularity() is True
        assert cache._enabled is True


def test_check_timestamp_granularity_linux_good():
    mock_stats = mock.Mock()
    mock_stats.f_timespec = 9  # nanosecond precision

    with (
        mock.patch("sys.platform", "linux"),
        mock.patch("os.statvfs", return_value=mock_stats),
    ):
        cache = ModelCache()
        assert cache._check_timestamp_granularity() is True
        assert cache._enabled is True


def test_check_timestamp_granularity_linux_poor():
    mock_stats = mock.Mock()
    mock_stats.f_timespec = 3  # millisecond precision

    with (
        mock.patch("sys.platform", "linux"),
        mock.patch("os.statvfs", return_value=mock_stats),
    ):
        cache = ModelCache()
        assert cache._check_timestamp_granularity() is False
        assert cache._enabled is False


def test_check_timestamp_granularity_linux_error():
    with (
        mock.patch("sys.platform", "linux"),
        mock.patch("os.statvfs", side_effect=OSError("Mock filesystem error")),
    ):
        cache = ModelCache()
        assert cache._check_timestamp_granularity() is False
        assert cache._enabled is False


def test_get_model_readonly(model_cache, test_path):
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime_ns = test_path.stat().st_mtime_ns

    # Set the model in the cache
    model_cache.set_model(test_path, model, mtime_ns)

    # Get the model in readonly mode
    readonly_model = model_cache.get_model(test_path, KilnModelTest, readonly=True)
    # Get a regular (copied/mutable) model
    copied_model = model_cache.get_model(test_path, KilnModelTest)

    # The readonly model should be the exact same instance as the cached model
    assert readonly_model is model_cache.model_cache[test_path][0]
    # While the regular get should be a different instance
    assert copied_model is not model_cache.model_cache[test_path][0]

    # Both should have the same data (but different readonly states)
    assert readonly_model.name == copied_model.name == model.name
    assert readonly_model.value == copied_model.value == model.value
    assert readonly_model._readonly is True  # Readonly model should be readonly
    assert copied_model._readonly is False  # Copied model should be mutable


def test_cached_models_marked_readonly(model_cache, test_path):
    """Test that models are marked as readonly when stored in cache."""
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    model = KilnModelTest(name="test_model", value=456)
    mtime_ns = test_path.stat().st_mtime_ns

    # Model should not be readonly initially
    assert model._readonly is False

    # Mark model as readonly before caching (this is what load_from_file does)
    model.mark_as_readonly()

    # Set the model in the cache
    model_cache.set_model(test_path, model, mtime_ns)

    # The original model should now be marked as readonly
    assert model._readonly is True

    # Get the model in readonly mode - should be the same instance
    readonly_model = model_cache.get_model(test_path, KilnModelTest, readonly=True)
    assert readonly_model is model  # Same instance
    assert readonly_model._readonly is True

    # Get the model in mutable mode - should be a copy
    mutable_model = model_cache.get_model(test_path, KilnModelTest, readonly=False)
    assert mutable_model is not model  # Different instance
    assert mutable_model._readonly is False

    # Should be able to mutate the copy
    mutable_model.name = "mutated_name"
    assert mutable_model.name == "mutated_name"

    # Original should remain unchanged
    assert model.name == "test_model"


def test_cache_mutable_model_raises_error(model_cache, test_path):
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    # Not readonly, so should raise error. The Cache should not allow mutable models to be cached.
    model = KilnModelTest(name="test", value=123)
    mtime_ns = test_path.stat().st_mtime_ns

    with pytest.raises(
        RuntimeError, match="Mutable models are not allowed to be cached"
    ):
        model_cache.set_model(test_path, model, mtime_ns)
