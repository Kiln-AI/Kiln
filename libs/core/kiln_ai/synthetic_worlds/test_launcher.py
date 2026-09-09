"""Tests for the launcher registry and LocalFilesLauncher: launch, finalize, release, prune."""

import os
import time
from datetime import datetime, timezone

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.synthetic_world import SyntheticInstance, SyntheticWorld
from kiln_ai.synthetic_worlds.launcher import (
    ACTIVE_MARKER,
    FIXTURE_MANIFEST,
    LocalFilesLauncher,
    UnknownLauncherError,
    _tree_digest,
    launcher_for_world,
    local_fixture_dir,
    register_launcher,
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


def make_fixture(world, fixture_id="alpha", manifest=None, files=("fixture.db",)):
    d = local_fixture_dir(world, fixture_id)
    d.mkdir(parents=True)
    for name in files:
        (d / name).write_bytes(b"0" * 100)
    (d / "nested").mkdir()
    (d / "nested" / "more.json").write_bytes(b"{}")
    if manifest is not None:
        import yaml

        (d / FIXTURE_MANIFEST).write_text(yaml.safe_dump(manifest))
    return d


@pytest.fixture
def launcher(tmp_path):
    return LocalFilesLauncher(cache_root=tmp_path / "cache", max_bytes=10_000)


class TestRegistry:
    def test_default_world_uses_local_files(self, world):
        assert isinstance(launcher_for_world(world), LocalFilesLauncher)

    def test_unknown_launcher_is_an_error(self, world):
        world.launcher = "matrix"
        with pytest.raises(UnknownLauncherError, match="matrix"):
            launcher_for_world(world)

    def test_registered_launcher_is_selected(self, world):
        class Fake:
            pass

        register_launcher("fake_test_launcher", Fake)  # type: ignore[arg-type]
        world.launcher = "fake_test_launcher"
        assert isinstance(launcher_for_world(world), Fake)


class TestFixtureDirs:
    def test_fixture_dir_under_world(self, world):
        assert (
            local_fixture_dir(world, "alpha")
            == world.world_dir() / "fixtures" / "alpha"
        )

    @pytest.mark.parametrize("bad", ["", " ", "../escape", "a/../../b", "."])
    def test_fixture_dir_rejects_escapes(self, world, bad):
        with pytest.raises(ValueError):
            local_fixture_dir(world, bad)

    def test_list_fixtures(self, world, launcher):
        assert launcher.list_fixtures(world) == []
        make_fixture(world, "b")
        make_fixture(world, "a")
        assert launcher.list_fixtures(world) == ["a", "b"]


class TestLaunch:
    async def test_launch_copies_fixture_and_reports_metadata(self, launcher, world):
        make_fixture(
            world, "alpha", manifest={"frozen_time": NOW.isoformat(), "plan": "pro"}
        )
        inst = await launcher.launch(world, {"fixture_id": "alpha"})
        assert inst.instance_id.startswith("inst_")
        assert inst.world_id == world.id
        assert inst.config == {"fixture_id": "alpha"}
        assert inst.source_path == str(local_fixture_dir(world, "alpha"))
        assert inst.metadata == {
            "fixture_id": "alpha",
            "frozen_time": NOW.isoformat(),
            "plan": "pro",
        }
        assert inst.framework_content_hash == "eng1"
        assert inst.world_lib_path is None
        copy = launcher.cache_root / inst.instance_id
        assert (copy / "fixture.db").read_bytes() == b"0" * 100
        assert (copy / "nested" / "more.json").exists()
        assert not (copy / FIXTURE_MANIFEST).exists()
        assert (copy / ACTIVE_MARKER).exists()

    async def test_config_scalars_override_manifest(self, launcher, world):
        make_fixture(world, "alpha", manifest={"frozen_time": NOW.isoformat()})
        inst = await launcher.launch(
            world,
            {
                "fixture_id": "alpha",
                "frozen_time": "2030-01-01T00:00:00+00:00",
                "nested": {"x": 1},
            },
        )
        assert inst.metadata["frozen_time"] == "2030-01-01T00:00:00+00:00"
        assert "nested" not in inst.metadata

    async def test_launch_exposes_world_lib_when_present(self, launcher, world):
        make_fixture(world)
        world.lib_dir().mkdir()
        inst = await launcher.launch(world, {"fixture_id": "alpha"})
        assert inst.world_lib_path == str(world.lib_dir())

    async def test_launch_requires_fixture_id(self, launcher, world):
        with pytest.raises(ValueError, match="fixture_id"):
            await launcher.launch(world, {})

    async def test_launch_unknown_fixture(self, launcher, world):
        with pytest.raises(ValueError, match="not found"):
            await launcher.launch(world, {"fixture_id": "nope"})

    async def test_launch_refuses_empty_fixture(self, launcher, world):
        local_fixture_dir(world, "empty").mkdir(parents=True)
        with pytest.raises(ValueError, match="no data files"):
            await launcher.launch(world, {"fixture_id": "empty"})

    async def test_instances_are_isolated(self, launcher, world):
        make_fixture(world)
        a = await launcher.launch(world, {"fixture_id": "alpha"})
        b = await launcher.launch(world, {"fixture_id": "alpha"})
        assert a.path != b.path
        (launcher.cache_root / a.instance_id / "fixture.db").write_bytes(b"changed")
        assert (
            launcher.cache_root / b.instance_id / "fixture.db"
        ).read_bytes() == b"0" * 100


class TestFinalizeAndRelease:
    async def test_finalize_marks_unchanged_but_keeps_copy(self, launcher, world):
        make_fixture(world, manifest={"frozen_time": NOW.isoformat()})
        inst = await launcher.launch(world, {"fixture_id": "alpha"})
        done = await launcher.finalize(inst)
        assert done.unchanged is True
        assert done.effective_path == inst.source_path
        copy = launcher.cache_root / inst.instance_id
        assert copy.is_dir()
        assert not (copy / ACTIVE_MARKER).exists()
        assert (await launcher.finalize(done)).unchanged is True
        await launcher.release(done)
        assert not copy.exists()

    async def test_finalize_keeps_changed_copy(self, launcher, world):
        make_fixture(world)
        inst = await launcher.launch(world, {"fixture_id": "alpha"})
        copy = launcher.cache_root / inst.instance_id
        (copy / "fixture.db").write_bytes(b"1" * 100)
        done = await launcher.finalize(inst)
        assert done.unchanged is False
        assert done.effective_path == str(copy)
        assert copy.is_dir()

    async def test_finalize_missing_dir_is_noop(self, launcher, world):
        make_fixture(world)
        inst = await launcher.launch(world, {"fixture_id": "alpha"})
        await launcher.release(inst)
        assert (await launcher.finalize(inst)).unchanged is False

    def test_tree_digest_ignores_marker_and_manifest(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        for d in (a, b):
            d.mkdir()
            (d / "x").write_bytes(b"same")
        (a / ACTIVE_MARKER).touch()
        (b / FIXTURE_MANIFEST).write_text("frozen_time: x\n")
        assert _tree_digest(a) == _tree_digest(b)
        (b / "x").write_bytes(b"diff")
        assert _tree_digest(a) != _tree_digest(b)


def _record(path, unchanged=False) -> SyntheticInstance:
    return SyntheticInstance(
        instance_id=path.name,
        world_id="w",
        path=str(path),
        source_path="/fixture",
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


class TestPrune:
    async def test_prune_deletes_unreferenced_and_keeps_referenced(self, launcher):
        root = launcher.cache_root
        kept = _make_dir(root, "inst_kept", 10)
        gone = _make_dir(root, "inst_gone", 10)
        await launcher.prune([_record(kept)])
        assert kept.is_dir()
        assert not gone.exists()

    async def test_prune_treats_unchanged_records_as_unreferenced(self, launcher):
        root = launcher.cache_root
        stale = _make_dir(root, "inst_stale", 10)
        await launcher.prune([_record(stale, unchanged=True)])
        assert not stale.exists()

    async def test_prune_spares_fresh_active_dirs(self, launcher):
        live = _make_dir(launcher.cache_root, "inst_live", 10, active=True)
        await launcher.prune([])
        assert live.is_dir()

    async def test_prune_enforces_size_cap_oldest_first(self, tmp_path):
        launcher = LocalFilesLauncher(cache_root=tmp_path / "cache", max_bytes=250)
        root = launcher.cache_root
        oldest = _make_dir(root, "inst_old", 100, age_s=300)
        middle = _make_dir(root, "inst_mid", 100, age_s=200)
        newest = _make_dir(root, "inst_new", 100, age_s=100)
        await launcher.prune([_record(oldest), _record(middle), _record(newest)])
        assert not oldest.exists()
        assert middle.is_dir()
        assert newest.is_dir()

    async def test_prune_without_cache_dir_is_noop(self, tmp_path):
        await LocalFilesLauncher(cache_root=tmp_path / "nope", max_bytes=1).prune([])

    def test_default_cap_from_config(self, tmp_path, monkeypatch):
        from kiln_ai.utils.config import Config

        monkeypatch.setattr(Config.shared(), "synthetic_instance_cache_max_gb", 0.5)
        assert LocalFilesLauncher(cache_root=tmp_path)._max_bytes == int(0.5 * 1024**3)
