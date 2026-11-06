import os
import sys
import threading
import time
from pathlib import Path

import pytest

from kiln_ai.datamodel.basemodel import KilnBaseModel
from kiln_ai.datamodel.model_cache import (
    FileIdentity,
    ModelCache,
    model_cache_enabled,
    set_model_cache_enabled,
)


class KilnModelTest(KilnBaseModel):
    name: str
    value: int


@pytest.fixture
def model_cache() -> ModelCache:
    return ModelCache(enabled=True)


@pytest.fixture
def test_path(tmp_path) -> Path:
    test_file = tmp_path / "test_model.kiln"
    test_file.write_text("original contents")
    return test_file


def readonly_model(name: str = "test", value: int = 123) -> KilnModelTest:
    model = KilnModelTest(name=name, value=value)
    model.mark_as_readonly()
    return model


def identity_of(path: Path) -> FileIdentity:
    identity = FileIdentity.from_path(path)
    assert identity is not None
    return identity


def cache_with_model(cache: ModelCache, path: Path) -> KilnModelTest:
    model = readonly_model()
    cache.set_model(path, model, identity_of(path))
    return model


def restore_mtime(path: Path, identity: FileIdentity) -> None:
    os.utime(path, ns=(identity.mtime_ns, identity.mtime_ns))


def test_disabled_by_default(test_path):
    for cache in (ModelCache(), ModelCache.shared()):
        assert cache.enabled is False
        cache_with_model(cache, test_path)
        assert cache.get_model(test_path, KilnModelTest, readonly=True) is None
        assert cache.get_model_id(test_path, KilnModelTest) is None


def test_set_enabled_false_clears(model_cache, test_path):
    cache_with_model(model_cache, test_path)

    model_cache.set_enabled(False)
    model_cache.set_enabled(True)

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None


def test_set_enabled_true_on_enabled_cache_keeps_entries(model_cache, test_path):
    model = cache_with_model(model_cache, test_path)

    model_cache.set_enabled(True)

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is model


def test_set_model_cache_enabled_switch(test_path):
    assert model_cache_enabled() is False

    set_model_cache_enabled(True)
    assert model_cache_enabled() is True
    assert ModelCache.shared().enabled is True
    model = cache_with_model(ModelCache.shared(), test_path)
    assert ModelCache.shared().get_model(test_path, KilnModelTest, readonly=True) is (
        model
    )

    set_model_cache_enabled(False)
    assert model_cache_enabled() is False
    set_model_cache_enabled(True)
    assert ModelCache.shared().get_model(test_path, KilnModelTest, readonly=True) is (
        None
    )


def test_hit_returns_same_instance_readonly_and_copy_mutable(model_cache, test_path):
    model = cache_with_model(model_cache, test_path)

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is model

    copy = model_cache.get_model(test_path, KilnModelTest)
    assert copy is not None
    assert copy is not model
    assert copy._readonly is False
    assert (copy.name, copy.value) == ("test", 123)

    copy.name = "mutated"

    assert model.name == "test"
    assert model._readonly is True
    cached = model_cache.get_model(test_path, KilnModelTest, readonly=True)
    assert cached is model


def test_get_model_id_returns_cached_id(model_cache, test_path):
    model = cache_with_model(model_cache, test_path)

    assert model_cache.get_model_id(test_path, KilnModelTest) == model.id

    test_path.write_text("different, longer contents")

    assert model_cache.get_model_id(test_path, KilnModelTest) is None


def test_changed_mtime_invalidates(model_cache, test_path):
    original = identity_of(test_path)
    cache_with_model(model_cache, test_path)

    os.utime(
        test_path, ns=(original.mtime_ns + 1_000_000, original.mtime_ns + 1_000_000)
    )
    changed = identity_of(test_path)
    assert (changed.size, changed.inode) == (original.size, original.inode)
    assert changed.mtime_ns != original.mtime_ns

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None


def test_changed_size_invalidates(model_cache, test_path):
    original = identity_of(test_path)
    cache_with_model(model_cache, test_path)

    test_path.write_text("different, longer contents")
    restore_mtime(test_path, original)
    changed = identity_of(test_path)
    assert (changed.mtime_ns, changed.inode) == (original.mtime_ns, original.inode)
    assert changed.size != original.size

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None


def test_replaced_file_new_inode_invalidates(model_cache, test_path):
    original = identity_of(test_path)
    cache_with_model(model_cache, test_path)

    replacement = test_path.with_name("replacement.kiln")
    replacement.write_text("replaced contents")
    assert replacement.stat().st_size == original.size
    os.replace(replacement, test_path)
    restore_mtime(test_path, original)
    changed = identity_of(test_path)
    assert (changed.mtime_ns, changed.size) == (original.mtime_ns, original.size)
    assert changed.inode != original.inode

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None


def test_deleted_file_invalidates(model_cache, test_path):
    cache_with_model(model_cache, test_path)

    test_path.unlink()

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None
    assert model_cache.get_model_id(test_path, KilnModelTest) is None


def test_invalidated_entry_stays_gone_when_file_returns(model_cache, test_path):
    original = identity_of(test_path)
    cache_with_model(model_cache, test_path)
    test_path.write_text("different, longer contents")
    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None

    test_path.write_text("original contents")
    restore_mtime(test_path, original)

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None


def test_wrong_type_raises_and_invalidates(model_cache, test_path):
    class AnotherModel(KilnBaseModel):
        other_field: str

    cache_with_model(model_cache, test_path)

    with pytest.raises(ValueError, match="is not of type AnotherModel"):
        model_cache.get_model(test_path, AnotherModel)

    assert model_cache.get_model(test_path, KilnModelTest) is None


def test_invalidate_model(model_cache, test_path):
    cache_with_model(model_cache, test_path)

    model_cache.invalidate(test_path)

    assert model_cache.get_model(test_path, KilnModelTest) is None


def test_clear_cache(model_cache, test_path):
    cache_with_model(model_cache, test_path)

    model_cache.clear()

    assert model_cache.get_model(test_path, KilnModelTest) is None


def test_cache_mutable_model_raises_error(model_cache, test_path):
    model = KilnModelTest(name="test", value=123)

    with pytest.raises(
        RuntimeError, match="Mutable models are not allowed to be cached"
    ):
        model_cache.set_model(test_path, model, identity_of(test_path))


def test_file_identity_from_path_missing_file_is_none(tmp_path):
    assert FileIdentity.from_path(tmp_path / "missing.kiln") is None


def test_file_identity_from_stat_matches_fstat(test_path):
    with open(test_path, "rb") as file:
        from_fstat = FileIdentity.from_stat(os.fstat(file.fileno()))

    assert from_fstat == FileIdentity.from_path(test_path)


def test_benchmark_get_model(benchmark, model_cache, test_path):
    cache_with_model(model_cache, test_path)

    def get_model():
        return model_cache.get_model(test_path, KilnModelTest, readonly=True)

    benchmark(get_model)
    stats = benchmark.stats.stats

    # 25k ops per second is the target. Getting 250k on Macbook, but CI will be slower
    target = 1 / 25000
    if stats.mean > target:
        pytest.fail(
            f"Average time per iteration: {stats.mean}, expected less than {target}"
        )


def test_concurrent_access_from_threads_does_not_raise(model_cache, test_path):
    """The shared cache is used from the event loop and from worker threads at once.

    A reader finds the entry, then another thread removes it before the reader
    indexes it. Or two readers both find the entry stale and both delete it. Both
    raised KeyError when the cache tested membership and then indexed or deleted.
    A tiny switch interval makes the interpreter change threads often enough to
    hit those windows in a short run.
    """
    model = readonly_model()
    fresh = identity_of(test_path)
    stale = FileIdentity(
        mtime_ns=fresh.mtime_ns - 1, size=fresh.size, inode=fresh.inode
    )
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
        model_cache.set_model(test_path, model, fresh)
        model_cache.invalidate(test_path)

    def store_stale():
        model_cache.set_model(test_path, model, stale)

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
