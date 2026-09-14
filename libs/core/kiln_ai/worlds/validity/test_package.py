from __future__ import annotations

import re
from pathlib import Path

import kiln_ai.worlds.validity as validity

PACKAGE = Path(__file__).parent

FORBIDDEN = re.compile(r"plane|company-v1|harness\.yaml", re.IGNORECASE)
"""The driver's vocabulary: the product, its fixture, and its config file. None of them is
this package's business anywhere, tests included, and a name that leaks into a docstring is
a name the next reader will follow into the code."""

FORBIDDEN_IN_MODULES = re.compile(
    r"gpt-|claude-|anthropic|openai|gemini", re.IGNORECASE
)
"""Model ids and providers, banned in the package's own modules. Not in the tests: a test
that builds a Kiln run config has to pass a real `ModelProviderName`, which is the
framework's own enum rather than anything about a world.

Both lists are tripwires for the names this project would plausibly leak, not proofs of
absence; the claim they support is in the package docstring."""


def sources() -> list[Path]:
    """Every source under the package except this one, which has to name what it bans."""
    return sorted(
        path for path in PACKAGE.rglob("*.py") if path.name != Path(__file__).name
    )


def test_package_has_no_plane_import():
    """The generic half measures any world. The moment a product name appears in here,
    the driver boundary has moved and phase 8's driver is no longer the only place that
    knows what is being replicated."""
    offenders = {
        path.name: [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if FORBIDDEN.search(line)
        ]
        for path in sources()
    }
    assert {name: lines for name, lines in offenders.items() if lines} == {}


def test_modules_name_no_model_or_provider():
    """The measurement is the same whatever answers the calls, so the package never names
    a model. The tests may: a Kiln run config needs a real provider enum."""
    offenders = {
        path.name: [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if FORBIDDEN_IN_MODULES.search(line)
        ]
        for path in sources()
        if not path.name.startswith(("test_", "conftest"))
    }
    assert {name: lines for name, lines in offenders.items() if lines} == {}


def test_every_module_is_reachable_from_the_package():
    modules = {
        path.stem for path in PACKAGE.glob("*.py") if not path.stem.startswith("test_")
    }
    modules -= {"__init__", "conftest"}
    assert modules == {
        "cost",
        "decision",
        "faults",
        "idmap",
        "metrics",
        "replay",
        "report",
        "scrub",
        "traces",
    }
    for name in modules:
        assert getattr(validity, name).__name__.endswith(name)


def test_exports_are_importable():
    for name in validity.__all__:
        assert hasattr(validity, name), name
