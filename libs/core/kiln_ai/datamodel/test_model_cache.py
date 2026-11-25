import sys
import threading
import time
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

    model_cache.set_model(test_path, model, mtime_ns, size_bytes=1)
    cached_model = model_cache.get_model(test_path, KilnModelTest)

    assert cached_model is not None
    assert cached_model.name == "test"
    assert cached_model.value == 123


def test_invalidate_model(model_cache, test_path):
    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime = test_path.stat().st_mtime

    model_cache.set_model(test_path, model, mtime, size_bytes=1)
    model_cache.invalidate(test_path)
    cached_model = model_cache.get_model(test_path, KilnModelTest)

    assert cached_model is None


def test_clear_cache(model_cache, test_path):
    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime = test_path.stat().st_mtime

    model_cache.set_model(test_path, model, mtime, size_bytes=1)
    model_cache.clear()
    cached_model = model_cache.get_model(test_path, KilnModelTest)

    assert cached_model is None


def test_cache_invalid_due_to_mtime_change(model_cache, test_path):
    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()  # Mark as readonly before caching
    mtime = test_path.stat().st_mtime

    model_cache.set_model(test_path, model, mtime, size_bytes=1)

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

    model_cache.set_model(test_path, model, mtime_ns, size_bytes=1)

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
    model_cache.set_model(test_path, model, mtime, size_bytes=1)

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
    model_cache.set_model(test_path, model, mtime_ns, size_bytes=1)

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
    model_cache.set_model(test_path, cached_model, mtime_ns, size_bytes=1)

    # Get the model again from the cache
    updated_cached_model = model_cache.get_model(test_path, KilnModelTest)

    # Assert that the updated cached model has the mutated values
    assert updated_cached_model.name == "mutated"
    assert updated_cached_model.value == 123


def test_no_cache_when_no_fine_granularity(model_cache, test_path):
    model = ModelTest(name="test", value=123)
    mtime_ns = test_path.stat().st_mtime_ns

    model_cache._enabled = False
    model_cache.set_model(test_path, model, mtime_ns, size_bytes=1)
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
    model_cache.set_model(test_path, model, mtime_ns, size_bytes=1)

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
    model_cache.set_model(test_path, model, mtime_ns, size_bytes=1)

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
        model_cache.set_model(test_path, model, mtime_ns, size_bytes=1)


def test_concurrent_access_from_threads_does_not_raise(model_cache, test_path):
    """The shared cache is used from the event loop and from worker threads at once.

    A reader finds the entry, then another thread removes it before the reader
    indexes it. Or two readers both find the entry stale and both delete it. Both
    raised KeyError when the cache tested membership and then indexed or deleted.
    A tiny switch interval makes the interpreter change threads often enough to
    hit those windows in a short run.
    """
    if not model_cache._enabled:
        pytest.skip("Cache is disabled on this fs")

    model = KilnModelTest(name="test", value=123)
    model.mark_as_readonly()
    fresh_mtime_ns = test_path.stat().st_mtime_ns
    stale_mtime_ns = fresh_mtime_ns - 1
    errors: list[BaseException] = []
    deadline = time.monotonic() + 0.5

    def run(step):
        try:
            while time.monotonic() < deadline:
                step()
        except BaseException as error:
            errors.append(error)

    def read():
        model_cache.get_model(test_path, KilnModelTest, readonly=True)
        model_cache.get_model_id(test_path, KilnModelTest)

    def store_then_invalidate():
        model_cache.set_model(test_path, model, fresh_mtime_ns, size_bytes=1)
        model_cache.invalidate(test_path)

    def store_stale():
        model_cache.set_model(test_path, model, stale_mtime_ns, size_bytes=1)

    steps = [read] * 4 + [store_then_invalidate] * 2 + [store_stale] * 2
    threads = [threading.Thread(target=run, args=(step,)) for step in steps]
    switch_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(switch_interval)

    assert errors == []


def _bounded_cache(max_bytes: int) -> ModelCache:
    cache = ModelCache(max_bytes=max_bytes)
    # Size accounting doesn't depend on timestamp granularity, which some CI filesystems lack.
    cache._enabled = True
    return cache


def _readonly_model(name: str = "test") -> KilnModelTest:
    model = KilnModelTest(name=name, value=1)
    model.mark_as_readonly()
    return model


@pytest.fixture
def cached_files(tmp_path):
    paths = []
    for i in range(4):
        path = tmp_path / f"model_{i}.kiln"
        path.touch()
        paths.append(path)
    return paths


def test_evicts_least_recently_used_when_over_max_bytes(cached_files):
    cache = _bounded_cache(300)
    a, b, c, d = cached_files
    for path in (a, b, c):
        cache.set_model(
            path, _readonly_model(), path.stat().st_mtime_ns, size_bytes=100
        )

    # Reading `a` makes `b` the least recently used entry.
    assert cache.get_model(a, KilnModelTest, readonly=True) is not None
    cache.set_model(d, _readonly_model(), d.stat().st_mtime_ns, size_bytes=100)

    assert list(cache.model_cache) == [c, a, d]
    assert cache.total_bytes == 300
    assert cache.get_model(b, KilnModelTest) is None


def test_evicts_several_entries_for_one_large_entry(cached_files):
    cache = _bounded_cache(300)
    a, b, c, d = cached_files
    for path in (a, b, c):
        cache.set_model(
            path, _readonly_model(), path.stat().st_mtime_ns, size_bytes=100
        )

    cache.set_model(d, _readonly_model(), d.stat().st_mtime_ns, size_bytes=250)

    assert list(cache.model_cache) == [d]
    assert cache.total_bytes == 250


def test_file_larger_than_max_bytes_is_not_cached(cached_files):
    cache = _bounded_cache(100)
    a, b, _, _ = cached_files
    cache.set_model(a, _readonly_model(), a.stat().st_mtime_ns, size_bytes=50)

    cache.set_model(b, _readonly_model(), b.stat().st_mtime_ns, size_bytes=101)

    assert list(cache.model_cache) == [a]
    assert cache.total_bytes == 50


def test_replacing_an_entry_counts_its_size_once(cached_files):
    cache = _bounded_cache(1000)
    a = cached_files[0]
    mtime_ns = a.stat().st_mtime_ns
    cache.set_model(a, _readonly_model(), mtime_ns, size_bytes=100)
    cache.set_model(a, _readonly_model("newer"), mtime_ns, size_bytes=40)

    assert cache.total_bytes == 40
    cached = cache.get_model(a, KilnModelTest, readonly=True)
    assert cached is not None
    assert cached.name == "newer"


def test_invalidate_and_clear_release_bytes(cached_files):
    cache = _bounded_cache(1000)
    a, b, _, _ = cached_files
    cache.set_model(a, _readonly_model(), a.stat().st_mtime_ns, size_bytes=100)
    cache.set_model(b, _readonly_model(), b.stat().st_mtime_ns, size_bytes=200)

    cache.invalidate(a)
    assert cache.total_bytes == 200
    cache.invalidate(a)
    assert cache.total_bytes == 200

    cache.clear()
    assert cache.total_bytes == 0
    assert len(cache.model_cache) == 0


def test_stale_entry_releases_bytes_on_read(cached_files):
    cache = _bounded_cache(1000)
    a = cached_files[0]
    cache.set_model(a, _readonly_model(), a.stat().st_mtime_ns - 1, size_bytes=100)

    assert cache.get_model(a, KilnModelTest) is None
    assert cache.total_bytes == 0


def test_file_exactly_max_bytes_is_cached(cached_files):
    cache = _bounded_cache(100)
    a = cached_files[0]

    cache.set_model(a, _readonly_model(), a.stat().st_mtime_ns, size_bytes=100)

    assert list(cache.model_cache) == [a]
    assert cache.total_bytes == 100
