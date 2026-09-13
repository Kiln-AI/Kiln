from __future__ import annotations

import os
import sqlite3
import stat
import sys

import pytest
import yaml

from . import fixtures as fixtures_module
from .conftest import FIXED_NOW
from .ctx import Ctx
from .errors import WorldBug
from .fixtures import SIDECAR_NAME, STATE_NAME, load, load_all, seal, verify

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


def add_two(instance) -> None:
    instance.call("add_item", name="one")
    instance.call("add_item", name="two")


def test_freeze_produces_rollback_journal_readonly_compact_file_and_sidecar(
    toy_world, frozen
):
    assert frozen.id == "base" and frozen.now == FIXED_NOW
    assert frozen.description == "two items" and frozen.parent_id is None
    assert not stat.S_IMODE(frozen.state_path.stat().st_mode) & stat.S_IWUSR

    conn = sqlite3.connect(f"file:{frozen.state_path}?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 2
    finally:
        conn.close()

    assert not (frozen.dir / f"{STATE_NAME}-wal").exists()
    sidecar = yaml.safe_load((frozen.dir / SIDECAR_NAME).read_text())
    assert sidecar["format_version"] == 1
    assert sidecar["world"] == "toy" and sidecar["world_version"] == "1.0.0"
    assert sidecar["schema_hash"] == toy_world.schema_hash
    assert sidecar["artifacts_sha256"] == {}
    verify(frozen)


def test_freeze_inside_transaction_refused(blank):
    with pytest.raises(WorldBug, match="inside a transaction"):
        with blank.bulk():
            blank.freeze("mid", "nope")


def test_freeze_refuses_existing_id_bad_id_nonconforming_schema(toy_world, frozen):
    instance = toy_world.instance("base")
    try:
        with pytest.raises(WorldBug, match="already lives"):
            instance.freeze("base", "again")
        with pytest.raises(WorldBug, match="single directory name"):
            instance.freeze("nested/id", "nope")
        with pytest.raises(WorldBug, match="single directory name"):
            instance.freeze(".hidden", "nope")
        instance.db.execute("CREATE TABLE sneaky (id TEXT PRIMARY KEY) STRICT")
        with pytest.raises(WorldBug, match="no longer matches the world's schema"):
            instance.freeze("drifted", "nope")
    finally:
        instance.destroy()
    assert not (toy_world.fixtures_dir / "drifted").exists()


def test_freeze_failure_leaves_no_pending_dir(toy_world, blank, monkeypatch):
    monkeypatch.setattr(
        fixtures_module,
        "file_sha256",
        lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError, match="boom"):
        blank.freeze("doomed", "nope")
    assert list(toy_world.fixtures_dir.glob(".pending-*")) == []
    assert not (toy_world.fixtures_dir / "doomed").exists()


def test_freeze_refuses_a_pending_directory_it_did_not_make(toy_world, blank):
    """The pending-then-rename dance exists so a fixture is never half-written; silently
    deleting someone else's pending directory would undo that."""
    pending = toy_world.fixtures_dir / ".pending-contested"
    pending.mkdir(parents=True)
    with pytest.raises(WorldBug, match="already exists"):
        blank.freeze("contested", "nope")
    assert pending.exists()
    assert not (toy_world.fixtures_dir / "contested").exists()


def test_verify_refuses_modified_file_and_caches(frozen):
    verify(frozen)
    fixtures_module._HASH_CACHE.clear()
    verify(frozen)
    assert frozen.state_path in fixtures_module._HASH_CACHE

    os.chmod(frozen.state_path, 0o644)
    frozen.state_path.write_bytes(b"not a database")
    with pytest.raises(WorldBug, match="has changed since it was frozen"):
        verify(frozen)


def test_seal_records_hashes_and_verify_checks_them(frozen, tmp_path):
    export = tmp_path / "export.json"
    export.write_text('{"items": []}')
    facts = tmp_path / "facts.yaml"
    facts.write_text("today: 2026-03-04\n")
    original_state = frozen.state_path.read_bytes()

    sealed = seal(frozen.dir, {"export.json": export, "facts.yaml": facts})
    assert set(sealed.artifacts_sha256) == {"export.json", "facts.yaml"}
    assert sealed.file_sha256 == frozen.meta.file_sha256
    assert frozen.state_path.read_bytes() == original_state
    for name in sealed.artifacts_sha256:
        assert not stat.S_IMODE((frozen.dir / name).stat().st_mode) & stat.S_IWUSR
    reloaded = load(frozen.dir)
    verify(reloaded)

    os.chmod(reloaded.dir / "export.json", 0o644)
    (reloaded.dir / "export.json").write_text('{"items": [1]}')
    with pytest.raises(WorldBug, match=r"export\.json has changed"):
        verify(reloaded)

    (reloaded.dir / "export.json").unlink()
    with pytest.raises(WorldBug, match=r"export\.json is recorded in the sidecar"):
        verify(reloaded)

    resealed = seal(reloaded.dir, {"facts.yaml": facts})
    assert set(resealed.artifacts_sha256) == {"facts.yaml"}
    verify(load(reloaded.dir))


def test_seal_rejects_bad_keys_before_writing(frozen, tmp_path):
    source = tmp_path / "export.json"
    source.write_text("{}")
    for bad in ("nested/export.json", STATE_NAME, SIDECAR_NAME, ".hidden"):
        with pytest.raises(WorldBug):
            seal(frozen.dir, {bad: source})
    with pytest.raises(WorldBug, match="no source file"):
        seal(frozen.dir, {"missing.json": tmp_path / "absent.json"})
    assert load(frozen.dir).meta.artifacts_sha256 == {}


def test_fixture_without_artifacts_key_loads_and_verifies(frozen):
    payload = yaml.safe_load((frozen.dir / SIDECAR_NAME).read_text())
    payload.pop("artifacts_sha256")
    (frozen.dir / SIDECAR_NAME).write_text(yaml.safe_dump(payload, sort_keys=True))
    reloaded = load(frozen.dir)
    assert reloaded.meta.artifacts_sha256 == {}
    verify(reloaded)


@pytest.mark.parametrize(
    "payload, message",
    [
        ("not: [a mapping", "not valid YAML"),
        ("just a string", "sidecar mapping"),
        ("format_version: 2\n", "format_version 2"),
        ("format_version: 1\nid: x\n", "not a valid fixture sidecar"),
    ],
)
def test_load_rejects_malformed_and_wrong_format_version(tmp_path, payload, message):
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / SIDECAR_NAME).write_text(payload)
    with pytest.raises(WorldBug, match=message):
        load(directory)


def test_load_missing_sidecar(tmp_path):
    with pytest.raises(WorldBug, match="not a fixture directory"):
        load(tmp_path / "nothing-here")


def test_load_all_skips_dot_dirs_refuses_duplicates(toy_world, frozen, tmp_path):
    (toy_world.fixtures_dir / ".pending-x").mkdir()
    (toy_world.fixtures_dir / "loose.txt").write_text("ignored")
    assert list(load_all(toy_world.fixtures_dir)) == ["base"]
    assert load_all(tmp_path / "no-such-dir") == {}

    duplicate = toy_world.fixtures_dir / "copy"
    duplicate.mkdir()
    (duplicate / SIDECAR_NAME).write_text((frozen.dir / SIDECAR_NAME).read_text())
    with pytest.raises(WorldBug, match="claim the id 'base'"):
        load_all(toy_world.fixtures_dir)


def test_fork_chain_of_three_preserves_parent_id(toy_world, frozen):
    first = fixtures_module.fork(
        toy_world, "base", "second", add_two, description="two more"
    )
    second = fixtures_module.fork(
        toy_world,
        "second",
        "third",
        lambda instance: instance.call("add_item", name="three"),
        description="one more",
    )
    assert first.parent_id == "base" and second.parent_id == "second"
    assert first.now == FIXED_NOW and second.now == FIXED_NOW

    instance = toy_world.instance("third")
    try:
        assert instance.db.one("SELECT count(*) AS n FROM items")["n"] == 5
    finally:
        instance.destroy()


def test_fork_generator_raise_leaves_nothing(toy_world, frozen):
    def explode(instance) -> None:
        instance.call("add_item", name="doomed")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        fixtures_module.fork(toy_world, "base", "doomed", explode, description="never")
    assert not (toy_world.fixtures_dir / "doomed").exists()
    assert list(toy_world.fixtures_dir.glob(".pending-*")) == []


def test_frozen_fixture_reloads_with_same_now_and_ids(toy_world, frozen):
    """A fixture's clock and seed source travel with it, so two instances agree."""

    def ids_of(instance) -> list[str]:
        return [instance.call("add_item", name=f"n{i}")["id"] for i in range(3)]

    first = toy_world.instance("base", seed=5)
    second = toy_world.instance("base", seed=5)
    try:
        assert first.clock.iso() == FIXED_NOW == second.clock.iso()
        assert ids_of(first) == ids_of(second)
    finally:
        first.destroy()
        second.destroy()


def test_control_tool_registration_is_refused_on_the_world(toy_world):
    with pytest.raises(WorldBug, match="reserved"):

        @toy_world.tool(name="controller_run_sql")
        def mine(ctx: Ctx) -> None:
            """Clash."""
