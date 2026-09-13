from __future__ import annotations

import sys

import pytest
import yaml

from .conftest import FIXED_NOW, build_toy_world
from .fixtures import SIDECAR_NAME
from .version import VERSION_FILE, compose, read_version, resolve, write_version

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


@pytest.fixture
def package(tmp_path):
    """A world package laid out the way `compose` expects: sources under `src/`,
    fixtures beside them."""
    root = tmp_path / "pkg"
    source = root / "src" / "toy_world"
    source.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'toy_world'\n")
    (source / "world.py").write_text("world = 1\n")
    (source / "schema").mkdir()
    (source / "schema" / "001.sql").write_text("CREATE TABLE t (id TEXT PRIMARY KEY);")
    (source / "notes.md").write_text("not a source file")
    (root / "fixtures").mkdir()
    return root


def test_compose_format_and_stability(package):
    composed = compose(package)
    assert composed == compose(package)
    engine, _, fixtures = composed.partition("+")
    assert engine.startswith("eng1:") and len(engine) == len("eng1:") + 16
    assert fixtures.startswith("g") and len(fixtures) == 13


def test_engine_part_moves_on_source_change_only(package):
    before = compose(package)
    (package / "src" / "toy_world" / "notes.md").write_text("edited prose")
    assert compose(package) == before

    (package / "src" / "toy_world" / "world.py").write_text("world = 2\n")
    after = compose(package)
    assert after != before
    assert after.split("+")[1] == before.split("+")[1]

    (package / "src" / "toy_world" / "schema" / "002.sql").write_text("-- more")
    assert compose(package).split("+")[0] != after.split("+")[0]


def test_fixtures_part_moves_on_freeze(tmp_path, package):
    world = build_toy_world(
        tmp_path, fixtures_dir=package / "fixtures", work_dir=tmp_path / "work"
    )
    before = compose(package)
    instance = world.instance(None, now=FIXED_NOW)
    try:
        instance.call("add_item", name="one")
        instance.freeze("first", "one item")
    finally:
        instance.destroy()
    after = compose(package)
    assert after.split("+")[0] == before.split("+")[0]
    assert after.split("+")[1] != before.split("+")[1]


def test_resolve_prefers_version_file(package):
    assert read_version(package) is None
    assert resolve(package) == compose(package)
    (package / VERSION_FILE).write_text("  pinned-by-build  \n")
    assert read_version(package) == "pinned-by-build"
    assert resolve(package) == "pinned-by-build"
    (package / VERSION_FILE).write_text("\n")
    assert read_version(package) is None
    assert resolve(package) == compose(package)


def test_write_version_after_freeze_matches_compose_and_engine_part_matches_sidecar(
    tmp_path, package
):
    world = build_toy_world(
        tmp_path, fixtures_dir=package / "fixtures", work_dir=tmp_path / "work"
    )
    world.set_version(write_version(package))
    instance = world.instance(None, now=FIXED_NOW)
    try:
        instance.call("add_item", name="one")
        fixture = instance.freeze("first", "one item")
    finally:
        instance.destroy()

    pinned = write_version(package)
    assert pinned == compose(package)
    assert read_version(package) == pinned

    sidecar = yaml.safe_load((fixture.dir / SIDECAR_NAME).read_text())
    # The fixture part necessarily lags by one freeze; the engine part must agree.
    assert sidecar["world_version"].split("+")[0] == pinned.split("+")[0]
    assert sidecar["world_version"].split("+")[1] != pinned.split("+")[1]


def test_compose_without_src_or_fixtures(tmp_path):
    empty = tmp_path / "bare"
    empty.mkdir()
    assert compose(empty) == compose(empty)
    assert compose(empty).startswith("eng1:")
