"""Environments were called worlds before release. A leftover old name compiles and
passes its own tests while disagreeing with every caller, so this checks every Python
identifier in the packages that used the feature for a `world` word. Only identifiers
are checked, never strings or comments, so English uses of "world" can't trip it."""

import ast
import re
from pathlib import Path

import kiln_ai
import kiln_server

_PACKAGE_DIRS = [
    Path(kiln_ai.__file__).parent,
    Path(kiln_server.__file__).parent,
    Path(__file__).parent / "studio_server",
]

# Identifiers where "world" is English, not the old feature name.
_ALLOWED = {
    "test_ending_block_is_unchanged_by_the_world_state_rules",
}

_OLD_TOOL_ID_PREFIX = "kiln_tool::world"


def _words(identifier: str) -> list[str]:
    """`_load_worldTarget2` -> ["load", "world", "target", "2"]."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", identifier)
    return [w.lower() for w in re.split(r"[_\s]+", spaced) if w]


def _uses_old_name(identifier: str) -> bool:
    if identifier in _ALLOWED:
        return False
    return any(word in ("world", "worlds") for word in _words(identifier))


def _identifiers(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            names.append(node.arg)
        elif isinstance(node, ast.alias):
            names.extend(part for part in node.name.split("."))
            if node.asname:
                names.append(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.extend(node.module.split("."))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _OLD_TOOL_ID_PREFIX in node.value:
                found.append((node.lineno, node.value))
            continue
        line = getattr(node, "lineno", 0)
        found.extend((line, name) for name in names if _uses_old_name(name))
    return found


def _python_sources() -> list[Path]:
    return sorted(path for d in _PACKAGE_DIRS for path in d.rglob("*.py"))


def test_identifier_check_catches_old_names():
    source = """
from kiln_ai.worlds.session_manager import WorldSessionManager
class World(Base): ...
def _uses_world(world_reset): ...
def validate_world_readiness(self): ...
world = load()
trace_key(a, b, world=world)
ctx.world.id
TOOL = "kiln_tool::world::w::t"
"""
    names = {name for _, name in _identifiers(ast.parse(source))}
    assert names >= {
        "worlds",
        "WorldSessionManager",
        "World",
        "_uses_world",
        "world_reset",
        "validate_world_readiness",
        "world",
        "kiln_tool::world::w::t",
    }


def test_identifier_check_ignores_english():
    source = '''
"""Parts of the world."""
greeting = "hello world"
texts = ["hello", "world"]  # world
'''
    assert _identifiers(ast.parse(source)) == []
    assert not _uses_old_name("worldwide")
    assert not _uses_old_name("test_ending_block_is_unchanged_by_the_world_state_rules")


def test_no_world_identifiers_remain():
    sources = _python_sources()
    assert sources, "no Python sources found; has the package layout changed?"
    hits = [
        f"{path}:{line}: {name}"
        for path in sources
        for line, name in _identifiers(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert hits == []
