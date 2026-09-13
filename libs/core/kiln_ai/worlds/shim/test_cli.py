from __future__ import annotations

import sys

import pytest
import yaml

from . import instances as instances_module
from .cli import main
from .conftest import FIXED_NOW
from .fixtures import load
from .instances import set_concurrency_gate
from .version import VERSION_FILE, compose

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)

MODULE_SOURCE = '''
from kiln_ai.worlds.shim import Ctx, World

SCHEMA = "CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL) STRICT;"
world = World("cliworld", "1.0.0", SCHEMA)
not_a_world = 7


@world.tool
def add(ctx: Ctx, name: str) -> dict:
    """Add an item."""
    ctx.db.execute("INSERT INTO items (id, name) VALUES (?, ?)", ctx.ids.uuid(), name)
    return {"name": name}


def seed(instance):
    instance.call("add", name="one")


def mutate(instance):
    instance.call("add", name="two")
'''


@pytest.fixture
def package(tmp_path):
    """An importable world package, on `sys.path` for the duration of the test."""
    root = tmp_path / "pkg"
    source = root / "src" / "cliworld"
    source.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'cliworld'\n")
    (source / "__init__.py").write_text("")
    (source / "world.py").write_text(MODULE_SOURCE)
    sys.path.insert(0, str(root / "src"))
    try:
        yield root
    finally:
        sys.path.remove(str(root / "src"))
        for name in [n for n in sys.modules if n.startswith("cliworld")]:
            del sys.modules[name]


@pytest.mark.parametrize(
    "argv, code",
    [(["--help"], 0), ([], 2), (["dance"], 2), (["freeze", "cliworld.world:world"], 2)],
)
def test_serve_help_and_exit_codes(argv, code, capsys):
    assert main(argv) == code


def test_freeze_round_trip_writes_version(package, capsys):
    code = main(
        [
            "freeze",
            "cliworld.world:world",
            "first",
            "--run",
            "cliworld.world:seed",
            "--description",
            "one item",
            "--now",
            FIXED_NOW,
        ]
    )
    assert code == 0
    fixture = load(package / "fixtures" / "first")
    assert fixture.now == FIXED_NOW and fixture.description == "one item"

    printed = capsys.readouterr().out
    assert yaml.safe_load(printed.split("\neng1:")[0])["id"] == "first"
    assert (package / VERSION_FILE).read_text().strip() == compose(package)
    assert compose(package) in printed


def test_fork_round_trip(package, capsys):
    assert (
        main(
            [
                "freeze",
                "cliworld.world:world",
                "first",
                "--run",
                "cliworld.world:seed",
                "--description",
                "one item",
                "--now",
                FIXED_NOW,
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "fork",
                "cliworld.world:world",
                "first",
                "second",
                "--run",
                "cliworld.world:mutate",
                "--description",
                "one more",
            ]
        )
        == 0
    )
    forked = load(package / "fixtures" / "second")
    assert forked.parent_id == "first" and forked.now == FIXED_NOW
    assert yaml.safe_load(capsys.readouterr().out.split("\neng1:")[0])["id"] == "second"

    import cliworld.world as module

    instance = module.world.instance("second")
    try:
        assert instance.db.one("SELECT count(*) AS n FROM items")["n"] == 2
    finally:
        instance.destroy()


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["serve", "no_such_module:world"], "could not import"),
        (["serve", "cliworld.world:missing"], "has no attribute"),
        (["serve", "cliworld.world:not_a_world"], "is not a World"),
        (["serve", "no_colon"], "module:attribute"),
        (
            [
                "freeze",
                "cliworld.world:world",
                "bad/id",
                "--run",
                "cliworld.world:seed",
                "--description",
                "x",
            ],
            "single directory name",
        ),
    ],
)
def test_bad_module_attr_one_line_error(package, capsys, argv, expected):
    assert main(argv) == 1
    captured = capsys.readouterr()
    assert expected in captured.err
    assert len(captured.err.strip().splitlines()) == 1
    assert "Traceback" not in captured.err


def test_serve_sets_gate_and_flags(package, monkeypatch):
    import uvicorn

    recorded: dict = {}

    def fake_run(app_object, **kwargs):
        recorded["app"] = app_object
        recorded.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    try:
        assert (
            main(
                [
                    "serve",
                    "cliworld.world:world",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8123",
                    "--concurrency",
                    "3",
                    "--include-control-tools",
                ]
            )
            == 0
        )
        assert recorded["host"] == "0.0.0.0" and recorded["port"] == 8123
        assert recorded["app"] is not None
        assert instances_module._GATE is not None
        assert instances_module._GATE._initial_value == 3
    finally:
        set_concurrency_gate(None)
