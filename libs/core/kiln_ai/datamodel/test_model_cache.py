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
from kiln_ai.datamodel.lazy_fields import DetachedValues
from kiln_ai.datamodel.model_cache import (
    EVICTION_TARGET_FRACTION,
    MEMORY_FACTOR,
    MIN_RECORD_BYTES,
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
# A record with large values, split into the part the cache keeps and the large values.
DETACHED_FILE_BYTES = 4000
LARGE_BYTES = 4000
DETACHED_NORMAL_BYTES = int(DETACHED_FILE_BYTES * MEMORY_FACTOR) - LARGE_BYTES
DETACHED_RECORD_BYTES = DETACHED_NORMAL_BYTES + LARGE_BYTES
LARGE_VALUES = {("body",): "a large value"}


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


def cache_with_detached(
    cache: ModelCache, path: Path, large_bytes: int = LARGE_BYTES
) -> object:
    """Cache a record as if `detach_large_values` took large values out of it; returns
    the owner token the large-value methods take."""
    owner = object()
    cache.set_model(
        path,
        readonly_model(),
        identity_of(path),
        DetachedValues(values=dict(LARGE_VALUES), size=large_bytes, owner=owner),
    )
    return owner


def drop_large_values(cache: ModelCache, path: Path) -> None:
    with cache._lock:
        if path in cache._loaded:
            cache._drop_large_values(path)


def restore_mtime(path: Path, identity: FileIdentity) -> None:
    os.utime(path, ns=(identity.mtime_ns, identity.mtime_ns))


def write_record_file(path: Path, size: int = RECORD_FILE_BYTES) -> Path:
    path.write_bytes(b"x" * size)
    return path


@pytest.fixture
def record_files(tmp_path) -> list[Path]:
    """Ten files of RECORD_FILE_BYTES each, so each cached record counts RECORD_BYTES."""
    return [write_record_file(tmp_path / f"record_{i}.kiln") for i in range(10)]


@pytest.fixture
def detached_files(tmp_path) -> list[Path]:
    """Files whose records, cached with LARGE_BYTES of large values, count
    DETACHED_RECORD_BYTES each."""
    return [
        write_record_file(tmp_path / f"detached_{i}.kiln", DETACHED_FILE_BYTES)
        for i in range(6)
    ]


def cache_with_budget_for(records: float) -> ModelCache:
    return ModelCache(enabled=True, budget_bytes=int(records * RECORD_BYTES))


def cached_paths(cache: ModelCache) -> list[Path]:
    """Cached paths, least recently used first."""
    return list(cache._records)


def loaded_paths(cache: ModelCache) -> list[Path]:
    """Paths whose large values are cached, least recently used first."""
    return list(cache._loaded)


def assert_accounting_consistent(cache: ModelCache) -> None:
    stats = cache.stats()
    entries = cache._records
    assert stats.records == len(entries)
    assert stats.records_with_large_values == len(cache._loaded)
    for path, entry in entries.items():
        assert (entry.large_values is not None) == (path in cache._loaded)
    assert set(cache._loaded) <= set(entries)
    assert stats.total_bytes == sum(
        entry.normal_bytes for entry in entries.values()
    ) + sum(entries[path].large_bytes for path in cache._loaded)
    assert stats.total_bytes <= stats.budget_bytes


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


def test_concurrent_access_from_threads_does_not_raise(
    model_cache, test_path, run_racing_threads
):
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
    run_racing_threads([threading.Thread(target=run, args=(step,)) for step in steps])

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
        f"Evicted the large values of 0 cached records and {evicted} whole records; "
        f"{stats.records} records (0 with large values) and "
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
    cache_with_detached(model_cache, removed, large_bytes=100)
    cache_with_model(model_cache, kept)

    remove(model_cache, removed)

    assert cached_paths(model_cache) == [kept]
    assert loaded_paths(model_cache) == []
    assert model_cache.stats().total_bytes == RECORD_BYTES


@pytest.mark.parametrize(
    "drop_all",
    [ModelCache.clear, lambda cache: cache.set_enabled(False)],
    ids=["clear", "disable"],
)
def test_dropping_everything_resets_accounting(model_cache, record_files, drop_all):
    for path in record_files[:3]:
        cache_with_model(model_cache, path)
    cache_with_detached(model_cache, record_files[3], large_bytes=100)

    drop_all(model_cache)

    stats = model_cache.stats()
    assert (stats.records, stats.records_with_large_values, stats.total_bytes) == (
        0,
        0,
        0,
    )


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
    owners: dict[Path, object] = {}

    def random_large_size() -> int:
        return rng.randint(1, (budget_records + 2) * RECORD_FILE_BYTES)

    def owner_or_stranger(path: Path) -> object:
        return owners.get(path) if rng.random() < 0.9 else object()

    def set_detached(path: Path) -> None:
        owners[path] = cache_with_detached(cache, path, random_large_size())

    operations: list[Callable[[Path], object]] = [
        lambda path: cache_with_model(cache, path),
        set_detached,
        set_detached,
        lambda path: cache.get_model(path, KilnModelTest, readonly=True),
        lambda path: cache.get_model_id(path, KilnModelTest),
        lambda path: cache.large_values_for(path, owner_or_stranger(path)),
        lambda path: cache.store_restored_values(
            path,
            owner_or_stranger(path),
            identity_of(path),
            LARGE_VALUES,
            random_large_size(),
        ),
        lambda path: drop_large_values(cache, path),
        lambda path: cache.drop_entry(path, owner_or_stranger(path)),
        cache.invalidate,
        lambda path: write_record_file(path, random_size()),
    ]

    most_with_large_values = 0
    for _ in range(2000):
        rng.choice(operations)(rng.choice(paths))
        assert_accounting_consistent(cache)
        most_with_large_values = max(
            most_with_large_values, cache.stats().records_with_large_values
        )
    assert cache.stats().records > 0
    assert most_with_large_values > 1


def test_concurrent_get_set_invalidate(tmp_path, run_racing_threads):
    paths = [write_record_file(tmp_path / f"record_{i}.kiln") for i in range(200)]
    identities = {path: identity_of(path) for path in paths}
    cache = cache_with_budget_for(20)
    model = readonly_model()
    owners: dict[Path, object] = {}
    errors: list[BaseException] = []
    deadline = time.monotonic() + 0.5

    def set_detached(path: Path) -> None:
        owner = object()
        owners[path] = owner
        cache.set_model(
            path,
            model,
            identities[path],
            DetachedValues(values=LARGE_VALUES, size=200, owner=owner),
        )

    def store_restored(path: Path) -> None:
        cache.store_restored_values(
            path, owners.get(path), identities[path], LARGE_VALUES, 200
        )

    def run(seed: int) -> None:
        rng = random.Random(seed)
        operations: list[Callable[[Path], object]] = [
            lambda path: cache.set_model(path, model, identities[path]),
            set_detached,
            lambda path: cache.get_model(path, KilnModelTest, readonly=True),
            lambda path: cache.get_model_id(path, KilnModelTest),
            lambda path: cache.large_values_for(path, owners.get(path)),
            store_restored,
            lambda path: drop_large_values(cache, path),
            lambda path: cache.drop_entry(path, owners.get(path)),
            cache.invalidate,
        ]
        try:
            while time.monotonic() < deadline:
                rng.choice(operations)(rng.choice(paths))
        except BaseException as error:
            errors.append(error)

    run_racing_threads(
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


def test_detached_entry_accounting(model_cache, detached_files, record_files):
    cache_with_detached(model_cache, detached_files[0])
    cache_with_detached(model_cache, detached_files[1], large_bytes=LARGE_BYTES * 2)
    model_cache.set_model(
        record_files[0],
        readonly_model(),
        identity_of(record_files[0]),
        DetachedValues(values={}, size=0, owner=object()),
    )

    first, second, nothing_detached = model_cache._records.values()
    assert (first.normal_bytes, first.large_bytes) == (
        DETACHED_NORMAL_BYTES,
        LARGE_BYTES,
    )
    assert second.normal_bytes == MIN_RECORD_BYTES
    assert (nothing_detached.normal_bytes, nothing_detached.large_owner) == (
        RECORD_BYTES,
        None,
    )
    stats = model_cache.stats()
    assert (stats.records, stats.records_with_large_values) == (3, 2)
    assert stats.total_bytes == (
        DETACHED_RECORD_BYTES + MIN_RECORD_BYTES + 2 * LARGE_BYTES + RECORD_BYTES
    )


def test_eviction_takes_large_values_first(detached_files):
    cache = ModelCache(enabled=True, budget_bytes=3 * DETACHED_RECORD_BYTES)

    for path in detached_files[:4]:
        cache_with_detached(cache, path)

    assert cached_paths(cache) == detached_files[:4]
    assert loaded_paths(cache) == detached_files[2:4]
    assert_accounting_consistent(cache)


def test_whole_records_evicted_once_no_large_values_remain(
    detached_files, record_files
):
    cache = ModelCache(
        enabled=True, budget_bytes=DETACHED_RECORD_BYTES + 2 * RECORD_BYTES
    )
    cache_with_detached(cache, detached_files[0])
    for path in record_files[:3]:
        cache_with_model(cache, path)
    assert loaded_paths(cache) == []
    assert cached_paths(cache) == [detached_files[0], *record_files[:3]]

    for path in record_files[3:6]:
        cache_with_model(cache, path)

    assert cached_paths(cache) == record_files[1:6]
    assert_accounting_consistent(cache)


def test_large_value_access_touches_lru_order(detached_files):
    cache = ModelCache(enabled=True, budget_bytes=3 * DETACHED_RECORD_BYTES)
    oldest, *others = detached_files[:3]
    owner = cache_with_detached(cache, oldest)
    for path in others:
        cache_with_detached(cache, path)

    assert cache.large_values_for(oldest, owner) == LARGE_VALUES
    cache_with_detached(cache, detached_files[3])

    assert loaded_paths(cache) == [oldest, detached_files[3]]
    assert cached_paths(cache) == [*others, oldest, detached_files[3]]


def test_large_values_larger_than_budget_served_not_kept(detached_files):
    path = detached_files[0]
    cache = ModelCache(enabled=True, budget_bytes=LARGE_BYTES - 1)
    owner = cache_with_detached(cache, path)

    assert cached_paths(cache) == [path]
    assert loaded_paths(cache) == []
    assert cache.stats().total_bytes == DETACHED_NORMAL_BYTES
    assert cache.large_values_for(path, owner) is None
    assert not cache.store_restored_values(
        path, owner, identity_of(path), LARGE_VALUES, LARGE_BYTES
    )
    assert cache.is_current_entry(path, owner)


def test_store_restored_values_rejects_stale_identity(model_cache, detached_files):
    path = detached_files[0]
    owner = cache_with_detached(model_cache, path)
    drop_large_values(model_cache, path)
    current = identity_of(path)
    stale = FileIdentity(
        mtime_ns=current.mtime_ns - 1, size=current.size, inode=current.inode
    )

    assert not model_cache.store_restored_values(
        path, owner, stale, LARGE_VALUES, LARGE_BYTES
    )
    assert loaded_paths(model_cache) == []


def test_store_restored_values_rejects_replaced_entry(model_cache, detached_files):
    path = detached_files[0]
    old_owner = cache_with_detached(model_cache, path)
    new_owner = cache_with_detached(model_cache, path)
    drop_large_values(model_cache, path)

    assert not model_cache.store_restored_values(
        path, old_owner, identity_of(path), LARGE_VALUES, LARGE_BYTES
    )
    assert model_cache.large_values_for(path, old_owner) is None
    assert not model_cache.is_current_entry(path, old_owner)
    assert model_cache.is_current_entry(path, new_owner)
    assert loaded_paths(model_cache) == []


def test_store_restored_values_second_writer_keeps_first(model_cache, detached_files):
    path = detached_files[0]
    owner = cache_with_detached(model_cache, path)
    drop_large_values(model_cache, path)
    first = {("body",): "first"}
    second = {("body",): "second"}

    assert model_cache.store_restored_values(
        path, owner, identity_of(path), first, LARGE_BYTES
    )
    assert model_cache.store_restored_values(
        path, owner, identity_of(path), second, LARGE_BYTES
    )

    assert model_cache.large_values_for(path, owner) is first
    assert_accounting_consistent(model_cache)


def test_store_restored_values_evicts_when_over_budget(detached_files, record_files):
    cache = ModelCache(enabled=True, budget_bytes=2 * DETACHED_RECORD_BYTES)
    restored, other = detached_files[:2]
    owner = cache_with_detached(cache, restored)
    cache_with_detached(cache, other)
    drop_large_values(cache, restored)
    cache_with_model(cache, record_files[0])

    assert cache.store_restored_values(
        restored, owner, identity_of(restored), LARGE_VALUES, LARGE_BYTES
    )

    assert loaded_paths(cache) == [restored]
    assert cached_paths(cache) == [other, record_files[0], restored]
    assert_accounting_consistent(cache)


def test_drop_entry_only_drops_owner(model_cache, detached_files):
    path = detached_files[0]
    owner = cache_with_detached(model_cache, path)

    model_cache.drop_entry(path, object())
    assert cached_paths(model_cache) == [path]

    model_cache.drop_entry(path, owner)
    assert cached_paths(model_cache) == []
    assert model_cache.stats().total_bytes == 0


def test_large_value_methods_when_disabled(model_cache, detached_files):
    path = detached_files[0]
    owner = cache_with_detached(model_cache, path)

    model_cache.set_enabled(False)

    assert model_cache.large_values_for(path, owner) is None
    assert not model_cache.store_restored_values(
        path, owner, identity_of(path), LARGE_VALUES, LARGE_BYTES
    )
    assert not model_cache.is_current_entry(path, owner)
    cache_with_detached(model_cache, path)
    assert model_cache.stats().records == 0
