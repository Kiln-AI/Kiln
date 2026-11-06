import logging
import os
import random
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from kiln_ai.datamodel.basemodel import KilnBaseModel
from kiln_ai.datamodel.model_cache import (
    EVICTION_TARGET_FRACTION,
    MEMORY_FACTOR,
    FileIdentity,
    ModelCache,
    default_cache_budget_bytes,
    model_cache_enabled,
    physical_memory_bytes,
    set_model_cache_enabled,
)

GIB = 1024**3
RECORD_FILE_BYTES = 1000
RECORD_BYTES = int(RECORD_FILE_BYTES * MEMORY_FACTOR)


class KilnModelTest(KilnBaseModel):
    name: str
    value: int


class OtherKilnModel(KilnBaseModel):
    other_field: str


@pytest.fixture
def model_cache() -> ModelCache:
    return ModelCache(enabled=True, budget_bytes=GIB)


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


def write_record_file(path: Path, size: int = RECORD_FILE_BYTES) -> Path:
    path.write_bytes(b"x" * size)
    return path


@pytest.fixture
def record_files(tmp_path) -> list[Path]:
    """Ten files of RECORD_FILE_BYTES each, so each cached record counts RECORD_BYTES."""
    return [write_record_file(tmp_path / f"record_{i}.kiln") for i in range(10)]


def cache_with_budget_for(records: float) -> ModelCache:
    return ModelCache(enabled=True, budget_bytes=int(records * RECORD_BYTES))


def cached_paths(cache: ModelCache) -> list[Path]:
    """Cached paths, least recently used first."""
    return list(cache._records)


def assert_accounting_consistent(cache: ModelCache) -> None:
    stats = cache.stats()
    assert stats.records == len(cache._records)
    assert stats.total_bytes == sum(
        entry.estimated_bytes for entry in cache._records.values()
    )
    assert stats.total_bytes <= stats.budget_bytes


def run_threads_with_frequent_switches(threads: list[threading.Thread]) -> None:
    """A tiny switch interval makes the interpreter change threads often enough to hit
    race windows in a short run."""
    switch_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(switch_interval)


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
    cache_with_model(model_cache, test_path)

    with pytest.raises(ValueError, match="is not of type OtherKilnModel"):
        model_cache.get_model(test_path, OtherKilnModel)

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
    run_threads_with_frequent_switches(
        [threading.Thread(target=run, args=(step,)) for step in steps]
    )

    assert errors == []


def test_entry_size_estimate_from_file_size(model_cache, tmp_path):
    cache_with_model(model_cache, write_record_file(tmp_path / "record.kiln", 2000))

    stats = model_cache.stats()
    assert (stats.records, stats.total_bytes) == (1, int(2000 * MEMORY_FACTOR))


def test_under_budget_add_does_not_evict(record_files):
    cache = cache_with_budget_for(3)

    with patch.object(cache, "_evict", wraps=cache._evict) as evict:
        for path in record_files[:3]:
            cache_with_model(cache, path)
        evict.assert_not_called()

        cache_with_model(cache, record_files[3])
        evict.assert_called_once()


def test_eviction_drops_least_recently_used_down_to_ninety_percent(
    record_files, caplog
):
    cache = cache_with_budget_for(len(record_files) - 1)

    with caplog.at_level(logging.DEBUG, logger="kiln_ai.datamodel.model_cache"):
        for path in record_files:
            cache_with_model(cache, path)

    stats = cache.stats()
    target = int(stats.budget_bytes * EVICTION_TARGET_FRACTION)
    # At the target, and one more record would have been over it.
    assert stats.total_bytes <= target < stats.total_bytes + RECORD_BYTES
    assert cached_paths(cache) == record_files[-stats.records :]
    evicted = len(record_files) - stats.records
    assert evicted > 1
    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == "kiln_ai.datamodel.model_cache"
    ] == [
        f"Evicted {evicted} cached records; {stats.records} records and "
        f"{stats.total_bytes} of {stats.budget_bytes} budget bytes remain"
    ]


@pytest.mark.parametrize(
    "read",
    [
        lambda cache, path: cache.get_model(path, KilnModelTest, readonly=True),
        lambda cache, path: cache.get_model(path, KilnModelTest),
        lambda cache, path: cache.get_model_id(path, KilnModelTest),
    ],
    ids=["readonly_get", "mutable_get", "get_model_id"],
)
def test_reads_protect_record_from_eviction(record_files, read):
    cache = cache_with_budget_for(3)
    oldest, *others = record_files[:3]
    for path in (oldest, *others):
        cache_with_model(cache, path)

    read(cache, oldest)
    cache_with_model(cache, record_files[3])

    assert oldest in cached_paths(cache)
    assert others[0] not in cached_paths(cache)


def test_record_larger_than_budget_is_not_kept(record_files):
    cache = cache_with_budget_for(3)
    kept, replaced = record_files[:2]
    cache_with_model(cache, kept)
    cache_with_model(cache, replaced)

    write_record_file(replaced, 4 * RECORD_FILE_BYTES)
    cache_with_model(cache, replaced)

    assert cached_paths(cache) == [kept]
    assert cache.stats().total_bytes == RECORD_BYTES


def test_replacing_entry_subtracts_old_size(model_cache, record_files):
    path = record_files[0]
    cache_with_model(model_cache, path)

    write_record_file(path, 2 * RECORD_FILE_BYTES)
    cache_with_model(model_cache, path)

    stats = model_cache.stats()
    assert (stats.records, stats.total_bytes) == (
        1,
        int(2 * RECORD_FILE_BYTES * MEMORY_FACTOR),
    )


def invalidate(cache: ModelCache, path: Path) -> None:
    cache.invalidate(path)


def read_after_file_changed(cache: ModelCache, path: Path) -> None:
    write_record_file(path, RECORD_FILE_BYTES + 1)
    assert cache.get_model(path, KilnModelTest, readonly=True) is None


def read_after_file_deleted(cache: ModelCache, path: Path) -> None:
    path.unlink()
    assert cache.get_model_id(path, KilnModelTest) is None


def read_as_wrong_type(cache: ModelCache, path: Path) -> None:
    with pytest.raises(ValueError):
        cache.get_model(path, OtherKilnModel)


@pytest.mark.parametrize(
    "remove",
    [invalidate, read_after_file_changed, read_after_file_deleted, read_as_wrong_type],
)
def test_removals_subtract_sizes(
    model_cache, record_files, remove: Callable[[ModelCache, Path], None]
):
    removed, kept = record_files[:2]
    cache_with_model(model_cache, removed)
    cache_with_model(model_cache, kept)

    remove(model_cache, removed)

    assert cached_paths(model_cache) == [kept]
    assert model_cache.stats().total_bytes == RECORD_BYTES


@pytest.mark.parametrize(
    "drop_all",
    [ModelCache.clear, lambda cache: cache.set_enabled(False)],
    ids=["clear", "disable"],
)
def test_dropping_everything_resets_accounting(model_cache, record_files, drop_all):
    for path in record_files[:3]:
        cache_with_model(model_cache, path)

    drop_all(model_cache)

    stats = model_cache.stats()
    assert (stats.records, stats.total_bytes) == (0, 0)


def test_accounting_matches_entries(tmp_path):
    """Sizes range up to past the budget, so some adds evict and some aren't kept."""
    rng = random.Random(1234)
    budget_records = 10

    def random_size() -> int:
        return rng.randint(100, (budget_records + 2) * RECORD_FILE_BYTES)

    paths = [
        write_record_file(tmp_path / f"record_{i}.kiln", random_size())
        for i in range(30)
    ]
    cache = cache_with_budget_for(budget_records)
    operations: list[Callable[[Path], object]] = [
        lambda path: cache_with_model(cache, path),
        lambda path: cache_with_model(cache, path),
        lambda path: cache.get_model(path, KilnModelTest, readonly=True),
        lambda path: cache.get_model_id(path, KilnModelTest),
        cache.invalidate,
        lambda path: write_record_file(path, random_size()),
    ]

    for _ in range(2000):
        rng.choice(operations)(rng.choice(paths))
        assert_accounting_consistent(cache)
    assert cache.stats().records > 0


def test_concurrent_get_set_invalidate(tmp_path):
    paths = [write_record_file(tmp_path / f"record_{i}.kiln") for i in range(200)]
    identities = {path: identity_of(path) for path in paths}
    cache = cache_with_budget_for(20)
    model = readonly_model()
    errors: list[BaseException] = []
    deadline = time.monotonic() + 0.5

    def run(seed: int) -> None:
        rng = random.Random(seed)
        operations: list[Callable[[Path], object]] = [
            lambda path: cache.set_model(path, model, identities[path]),
            lambda path: cache.get_model(path, KilnModelTest, readonly=True),
            lambda path: cache.get_model_id(path, KilnModelTest),
            cache.invalidate,
        ]
        try:
            while time.monotonic() < deadline:
                rng.choice(operations)(rng.choice(paths))
        except BaseException as error:
            errors.append(error)

    run_threads_with_frequent_switches(
        [threading.Thread(target=run, args=(seed,)) for seed in range(8)]
    )

    assert errors == []
    assert_accounting_consistent(cache)


def test_entry_replaced_during_freshness_stat_is_kept_but_not_served(
    model_cache, test_path
):
    cache_with_model(model_cache, test_path)
    replacement = readonly_model(name="replacement")
    real_from_path = FileIdentity.from_path

    def replace_entry_then_stat(path: Path) -> FileIdentity | None:
        identity = real_from_path(path)
        assert identity is not None
        model_cache.set_model(path, replacement, identity)
        return identity

    with patch.object(FileIdentity, "from_path", side_effect=replace_entry_then_stat):
        assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is None

    assert model_cache.get_model(test_path, KilnModelTest, readonly=True) is (
        replacement
    )


@pytest.mark.parametrize(
    "ram, budget",
    [(4 * GIB, int(0.2 * 4 * GIB)), (16 * GIB, 2 * GIB), (None, 1 * GIB)],
)
def test_default_budget_formula(ram, budget):
    with patch("kiln_ai.datamodel.model_cache.physical_memory_bytes", return_value=ram):
        assert default_cache_budget_bytes() == budget


def test_budget_defaults_to_default_cache_budget_bytes():
    with patch(
        "kiln_ai.datamodel.model_cache.default_cache_budget_bytes", return_value=12345
    ):
        assert ModelCache().stats().budget_bytes == 12345
        assert ModelCache.shared().stats().budget_bytes == 12345
        assert ModelCache(budget_bytes=99).stats().budget_bytes == 99


def test_physical_memory_bytes_reads_this_machine():
    ram = physical_memory_bytes()

    assert ram is not None
    assert ram > 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX reads RAM from os.sysconf")
@pytest.mark.parametrize(
    "sysconf_values, expected",
    [
        ({"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 1000}, 4096 * 1000),
        ({"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": -1}, None),
        ({"SC_PAGE_SIZE": -1, "SC_PHYS_PAGES": -1}, None),
        ({}, None),
    ],
    ids=["known", "unknown_pages", "both_unknown", "unsupported_name"],
)
def test_physical_memory_bytes_from_sysconf(sysconf_values, expected):
    def sysconf(name: str) -> int:
        if name not in sysconf_values:
            raise ValueError(f"unrecognized configuration name {name}")
        return sysconf_values[name]

    with patch.object(os, "sysconf", side_effect=sysconf):
        assert physical_memory_bytes() == expected
