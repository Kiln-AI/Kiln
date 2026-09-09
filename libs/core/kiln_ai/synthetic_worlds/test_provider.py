"""Tests for LocalCopyProvider: create, finalize (drop unchanged), prune, size cap."""

import os
import time
from datetime import datetime, timezone

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.synthetic_world import (
    SyntheticFixture,
    SyntheticInstance,
    SyntheticWorld,
)
from kiln_ai.synthetic_worlds.provider import (
    ACTIVE_MARKER,
    LocalCopyProvider,
    _tree_digest,
)

NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


@pytest.fixture
def world(tmp_path):
    project = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    project.path.parent.mkdir(parents=True)
    project.save_to_file()
    w = SyntheticWorld(name="w", parent=project, framework_content_hash="eng1")
    w.save_to_file()
    return w


@pytest.fixture
def fixture(world):
    f = SyntheticFixture(name="f", parent=world, frozen_time=NOW)
    f.save_to_file()
    f.data_dir().mkdir()
    (f.data_dir() / "fixture.db").write_bytes(b"0" * 100)
    (f.data_dir() / "nested").mkdir()
    (f.data_dir() / "nested" / "more.json").write_bytes(b"{}")
    return f


@pytest.fixture
def provider(tmp_path):
    return LocalCopyProvider(cache_root=tmp_path / "cache", max_bytes=10_000)


async def test_create_copies_fixture_data(provider, world, fixture):
    inst = await provider.create(world, fixture, frozen_time=NOW)
    assert inst.instance_id.startswith("inst_")
    assert inst.world_id == world.id and inst.fixture_id == fixture.id
    assert inst.fixture_data_path == str(fixture.data_dir())
    assert inst.frozen_time == NOW
    assert inst.framework_content_hash == "eng1"
    assert inst.world_lib_path is None
    copy = provider.cache_root / inst.instance_id
    assert (copy / "fixture.db").read_bytes() == b"0" * 100
    assert (copy / "nested" / "more.json").exists()
    assert (copy / ACTIVE_MARKER).exists()


async def test_create_exposes_world_lib_when_present(provider, world, fixture):
    world.lib_dir().mkdir()
    inst = await provider.create(world, fixture, frozen_time=None)
    assert inst.world_lib_path == str(world.lib_dir())


async def test_create_refuses_empty_fixture(provider, world):
    f = SyntheticFixture(name="empty", parent=world)
    f.save_to_file()
    with pytest.raises(ValueError, match="has no data/"):
        await provider.create(world, f, frozen_time=None)


async def test_instances_are_isolated(provider, world, fixture):
    a = await provider.create(world, fixture, frozen_time=None)
    b = await provider.create(world, fixture, frozen_time=None)
    assert a.path != b.path
    (provider.cache_root / a.instance_id / "fixture.db").write_bytes(b"changed")
    assert (provider.cache_root / b.instance_id / "fixture.db").read_bytes() == (
        b"0" * 100
    )


async def test_finalize_marks_unchanged_copy_but_keeps_it(provider, world, fixture):
    """The copy stays until the runner destroys it: a concurrent grader may be reading."""
    inst = await provider.create(world, fixture, frozen_time=None)
    done = await provider.finalize(inst)
    assert done.unchanged is True
    assert done.effective_path == str(fixture.data_dir())
    copy = provider.cache_root / inst.instance_id
    assert copy.is_dir()
    assert not (copy / ACTIVE_MARKER).exists()
    # Idempotent on an already-settled record.
    assert (await provider.finalize(done)).unchanged is True
    await provider.destroy(done)
    assert not copy.exists()


async def test_finalize_keeps_changed_copy(provider, world, fixture):
    inst = await provider.create(world, fixture, frozen_time=None)
    copy = provider.cache_root / inst.instance_id
    (copy / "fixture.db").write_bytes(b"1" * 100)
    done = await provider.finalize(inst)
    assert done.unchanged is False
    assert copy.is_dir()
    assert not (copy / ACTIVE_MARKER).exists()


async def test_finalize_missing_dir_is_noop(provider, world, fixture):
    inst = await provider.create(world, fixture, frozen_time=None)
    await provider.destroy(inst)
    assert (await provider.finalize(inst)).unchanged is False


def test_tree_digest_ignores_marker_and_sees_content(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "x").write_bytes(b"same")
    (a / ACTIVE_MARKER).touch()
    assert _tree_digest(a) == _tree_digest(b)
    (b / "x").write_bytes(b"diff")
    assert _tree_digest(a) != _tree_digest(b)


def _record(path, unchanged=False) -> SyntheticInstance:
    return SyntheticInstance(
        instance_id=path.name,
        world_id="w",
        fixture_id="f",
        path=str(path),
        fixture_data_path="/fixture",
        unchanged=unchanged,
    )


def _make_dir(root, name, size, age_s=0.0, active=False):
    d = root / name
    d.mkdir(parents=True)
    (d / "fixture.db").write_bytes(b"x" * size)
    if active:
        (d / ACTIVE_MARKER).touch()
    stamp = time.time() - age_s
    os.utime(d, (stamp, stamp))
    return d


async def test_prune_deletes_unreferenced_and_keeps_referenced(provider):
    root = provider.cache_root
    kept = _make_dir(root, "inst_kept", 10)
    gone = _make_dir(root, "inst_gone", 10)
    await provider.prune([_record(kept)])
    assert kept.is_dir()
    assert not gone.exists()


async def test_prune_ignores_unchanged_records_paths(provider):
    """An `unchanged` record's copy was already deleted; a stale dir by that name is junk."""
    root = provider.cache_root
    stale = _make_dir(root, "inst_stale", 10)
    await provider.prune([_record(stale, unchanged=True)])
    assert not stale.exists()


async def test_prune_spares_fresh_active_dirs(provider):
    root = provider.cache_root
    live = _make_dir(root, "inst_live", 10, active=True)
    await provider.prune([])
    assert live.is_dir()


async def test_prune_enforces_size_cap_oldest_first(tmp_path):
    provider = LocalCopyProvider(cache_root=tmp_path / "cache", max_bytes=250)
    root = provider.cache_root
    oldest = _make_dir(root, "inst_old", 100, age_s=300)
    middle = _make_dir(root, "inst_mid", 100, age_s=200)
    newest = _make_dir(root, "inst_new", 100, age_s=100)
    await provider.prune([_record(oldest), _record(middle), _record(newest)])
    assert not oldest.exists()
    assert middle.is_dir()
    assert newest.is_dir()


async def test_prune_without_cache_dir_is_noop(tmp_path):
    provider = LocalCopyProvider(cache_root=tmp_path / "nope", max_bytes=1)
    await provider.prune([])


def test_default_cap_from_config(tmp_path, monkeypatch):
    from kiln_ai.utils.config import Config

    monkeypatch.setattr(Config.shared(), "synthetic_instance_cache_max_gb", 0.5)
    provider = LocalCopyProvider(cache_root=tmp_path)
    assert provider._max_bytes == int(0.5 * 1024**3)
