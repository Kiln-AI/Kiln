from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

from . import instances as instances_module
from . import world as world_module
from .conftest import TOY_SCHEMA, build_toy_world
from .ctx import Ctx
from .errors import WorldBug
from .instances import WORK_ROOT_NAME
from .tool import Tool
from .world import World, sql_files

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


def import_from(tmp_path: Path, relative: str, source: str, module_name: str):
    """Write a module under `tmp_path`, import it, and return it."""
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    sys.path.insert(0, str(path.parent))
    try:
        sys.modules.pop(module_name, None)
        return importlib.import_module(module_name)
    finally:
        sys.path.remove(str(path.parent))
        sys.modules.pop(module_name, None)


def test_python_floor_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(world_module.sys, "version_info", (3, 11, 9))
    with pytest.raises(WorldBug, match=r"3\.12 or newer"):
        World("toy", "1", TOY_SCHEMA, fixtures_dir=tmp_path)


def test_ddl_failure_message(tmp_path):
    with pytest.raises(WorldBug, match="schema failed to run"):
        World("toy", "1", "CREATE TABLE (;", fixtures_dir=tmp_path)


def test_empty_version_refused(tmp_path):
    with pytest.raises(WorldBug, match="non-empty version"):
        World("toy", "", TOY_SCHEMA, fixtures_dir=tmp_path)


WORLD_SOURCE = (
    "from kiln_ai.worlds.shim import World\n"
    "world = World('derived', '1', 'CREATE TABLE t (id TEXT PRIMARY KEY) STRICT;')\n"
)


def test_fixtures_dir_derivation_src_layout_explicit_and_no_pyproject(tmp_path):
    package = tmp_path / "pkg"
    (package / "src" / "derived").mkdir(parents=True)
    (package / "pyproject.toml").write_text("[project]\nname = 'derived'\n")
    module = import_from(package, "src/derived/world_a.py", WORLD_SOURCE, "world_a")
    assert module.world.fixtures_dir == package / "fixtures"

    loose = tmp_path / "loose"
    loose.mkdir()
    module = import_from(loose, "world_b.py", WORLD_SOURCE, "world_b")
    assert module.world.fixtures_dir == loose / "fixtures"

    explicit = World(
        "explicit", "1", TOY_SCHEMA, fixtures_dir=tmp_path / "somewhere-else"
    )
    assert explicit.fixtures_dir == tmp_path / "somewhere-else"


def test_default_work_dir_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(
        instances_module.tempfile, "gettempdir", lambda: str(tmp_path / "tmp")
    )
    world = World("layout", "1", TOY_SCHEMA, fixtures_dir=tmp_path / "fixtures")
    instance = world.instance(None)
    try:
        expected = (
            Path(tempfile.gettempdir())
            / WORK_ROOT_NAME
            / str(os.getpid())
            / "layout"
            / instance.id
        )
        assert instance.dir == expected
        assert instance.dir.is_dir()
    finally:
        instance.destroy()


def test_duplicate_reserved_and_control_names_refused(toy_world):
    with pytest.raises(WorldBug, match="already registered"):

        @toy_world.tool
        def add_item(ctx: Ctx, name: str) -> None:
            """Clash."""

    for reserved in ("reset", "step", "state", "close", "controller_digest"):
        with pytest.raises(WorldBug, match="reserved"):
            toy_world.tool(lambda ctx: None, name=reserved)


def test_tool_object_with_options_refused(toy_world):
    def standalone(ctx: Ctx) -> None:
        """Standalone."""

    built = Tool.from_function(standalone)
    toy_world.tool(built)
    assert toy_world.tools["standalone"] is built

    another = Tool.from_function(standalone, name="another")
    with pytest.raises(WorldBug, match="built already"):
        toy_world.tool(another, name="renamed")


def test_late_tool_and_middleware_reach_existing_instance(toy_world, blank):
    seen: list[str] = []

    @toy_world.tool
    def late(ctx: Ctx) -> str:
        """Registered after the instance existed."""
        return "late"

    @toy_world.middleware
    def watch(ctx, call, next_handler):
        seen.append(call.name)
        return next_handler(ctx, call)

    assert blank.call("late") == "late"
    assert seen == ["late"]


def test_decorator_and_call_forms(tmp_path):
    world = World("forms", "1", TOY_SCHEMA, fixtures_dir=tmp_path)

    @world.tool
    def bare(ctx: Ctx) -> None:
        """Bare."""

    @world.tool(name="renamed", description="Given.")
    def with_options(ctx: Ctx) -> None:
        """Ignored."""

    def plain(ctx: Ctx) -> None:
        """Plain."""

    assert world.tool(plain) is plain
    assert set(world.tools) >= {"bare", "renamed", "plain"}
    assert world.tools["renamed"].description == "Given."
    assert callable(bare) and callable(with_options)


def test_middleware_shape_check(toy_world):
    with pytest.raises(WorldBug, match=r"\(ctx, call, next_handler\)"):

        @toy_world.middleware
        def too_few(ctx, call):
            return None

    @toy_world.middleware
    def variadic(*args):
        return args[2](args[0], args[1])

    assert toy_world.middlewares[-1] is variadic


def test_startup_hook_signature_rules_and_accepted_kwargs(tmp_path):
    world = World("hooks", "1", TOY_SCHEMA, fixtures_dir=tmp_path)
    assert world.accepted_startup_kwargs == frozenset()

    @world.instance_startup
    def one(ctx: Ctx, *, owner: str = "nobody") -> None: ...

    assert world.accepted_startup_kwargs == frozenset({"owner"})

    @world.instance_startup
    def two(ctx: Ctx, *, region: str = "eu") -> None: ...

    assert world.accepted_startup_kwargs == frozenset({"owner", "region"})

    with pytest.raises(WorldBug, match="only positional argument"):
        world.instance_startup(lambda ctx, other: None)
    with pytest.raises(WorldBug, match="reset already means"):
        world.instance_startup(lambda ctx, *, fixture=None: None)

    @world.instance_startup
    def anything(ctx: Ctx, **kwargs) -> None: ...

    assert world.accepted_startup_kwargs is None


def test_table_without_pk_refused_unless_untracked(tmp_path):
    schema = "CREATE TABLE loose (a TEXT, b TEXT) STRICT;"
    with pytest.raises(WorldBug, match="no explicit primary key"):
        World("pk", "1", schema, fixtures_dir=tmp_path)
    world = World("pk", "1", schema, fixtures_dir=tmp_path, untracked_tables=("loose",))
    assert world.tracked_tables == ()


@pytest.mark.parametrize(
    "schema, accepted",
    [
        ("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT) STRICT;", True),
        ("CREATE TABLE t (k TEXT NOT NULL PRIMARY KEY, v TEXT);", True),
        ("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT) WITHOUT ROWID;", True),
        # An INTEGER primary key is the rowid: SQLite fills it in, so it is never NULL.
        ("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT);", True),
        # DESC makes the column a real indexed key rather than the rowid, and it can be NULL.
        ("CREATE TABLE t (k INTEGER PRIMARY KEY DESC, v TEXT);", False),
        ("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT);", False),
        ("CREATE TABLE t (a TEXT, b TEXT NOT NULL, PRIMARY KEY (a, b));", False),
    ],
)
def test_nullable_primary_key_refused(tmp_path, schema, accepted):
    """A NULL key would make the diff's null-safe join match unrelated rows, so `changes()`
    would report edits nobody made. Caught at construction instead."""
    if accepted:
        assert World("nulls", "1", schema, fixtures_dir=tmp_path).tracked_tables == (
            "t",
        )
    else:
        with pytest.raises(WorldBug, match="allows NULL in primary key"):
            World("nulls", "1", schema, fixtures_dir=tmp_path)


def test_nullable_primary_key_allowed_when_untracked(tmp_path):
    world = World(
        "nulls",
        "1",
        "CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT);",
        fixtures_dir=tmp_path,
        untracked_tables=("t",),
    )
    assert world.tracked_tables == ()


def test_untracked_table_must_exist(tmp_path):
    with pytest.raises(WorldBug, match=r"untracked_tables names \['countrs'\]"):
        World(
            "typo",
            "1",
            TOY_SCHEMA,
            fixtures_dir=tmp_path,
            untracked_tables=("countrs",),
        )


def test_tracked_tables_excludes_untracked(toy_world):
    assert toy_world.tracked_tables == ("items", "tags")
    assert toy_world.untracked_tables == ("counters",)


def test_sql_files_sorted_concatenation(tmp_path):
    package = tmp_path / "sqlpkg"
    (package / "schema").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "schema" / "002_second.sql").write_text("SECOND")
    (package / "schema" / "001_first.sql").write_text("FIRST")
    (package / "schema" / "notes.txt").write_text("IGNORED")
    sys.path.insert(0, str(tmp_path))
    try:
        sys.modules.pop("sqlpkg", None)
        assert sql_files("sqlpkg", "schema") == "FIRST\nSECOND"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("sqlpkg", None)


def test_fixtures_lists_and_fixture_by_id(toy_world, frozen):
    assert [f.id for f in toy_world.fixtures()] == ["base"]
    assert toy_world.fixture("base").state_path == frozen.state_path
    with pytest.raises(WorldBug, match="has no fixture 'missing'"):
        toy_world.fixture("missing")
    with pytest.raises(WorldBug, match="single directory name"):
        toy_world.fixture("../escape")


def test_set_version_replaces_and_refuses_empty(toy_world):
    toy_world.set_version("2.0.0+fault.x")
    assert toy_world.version == "2.0.0+fault.x"
    with pytest.raises(WorldBug, match="cannot be empty"):
        toy_world.set_version("")


def test_control_tools_registered_on_every_world(tmp_path):
    world = build_toy_world(tmp_path)
    control = {name for name, tool in world.tools.items() if tool.control}
    assert control == {
        "controller_run_sql",
        "controller_changes",
        "controller_digest",
    }
