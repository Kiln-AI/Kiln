"""Regression tests for the kiln_ai import graph.

``kiln_ai.utils.open_ai_types`` once imported ``MessageUsage`` from
``kiln_ai.datamodel.usage`` and raised a circular-import ``ImportError``
whenever it was the first kiln module imported. ``kiln_ai/utils/usage.py``
documents that cycle and the layering rule that breaks it; these tests
enforce the rule. An eager ``from . import (...)`` in
``kiln_ai/adapters/__init__.py`` masked the bug by always loading
``kiln_ai.datamodel`` first, so it only surfaces once that init goes lazy.

Every case runs in a fresh interpreter, because import order inside the
pytest process is already fixed by whatever the rest of the suite imported.
"""

import ast
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

# .../libs/core, the directory dotted module paths are relative to.
CORE_ROOT = Path(__file__).parent.parent.parent
DATAMODEL_DIR = CORE_ROOT / "kiln_ai" / "datamodel"
UTILS_PACKAGE = "kiln_ai.utils"

# Source appended to the child's `-c`, run after the module under test is
# imported. stdout is this probe's return channel back to the parent, so it
# writes the verdict there directly rather than routing IPC through the print
# builtin, which the repo's debug-statement screen matches.
#
# The leading newline keeps the verdict on a line of its own even when
# something else left stdout mid-line, which is what lets _verdict_from
# tolerate noise ahead of it.
_REPORT_DATAMODEL_LOADED = (
    "import sys;"
    " loaded = any(name == 'kiln_ai.datamodel'"
    " or name.startswith('kiln_ai.datamodel.') for name in sys.modules);"
    " sys.stdout.write('\\n' + str(loaded))"
)


# A fresh kiln import takes well under a second; this only has to be short
# enough that a genuinely hung import fails the suite instead of stalling it.
_IMPORT_TIMEOUT_SECONDS = 120


def assert_imports_cleanly(module: str) -> subprocess.CompletedProcess[str]:
    """Assert `module` can be imported as the very first kiln module, in a
    fresh interpreter, and return the completed run.

    This is where a reintroduced cycle surfaces: Python raises ImportError on
    the partially initialized module, and the child's stderr becomes the
    failure message.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}; {_REPORT_DATAMODEL_LOADED}"],
        capture_output=True,
        text=True,
        timeout=_IMPORT_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, f"importing {module} first failed:\n{result.stderr}"
    return result


def _verdict_from(stdout: str) -> bool:
    """Read the probe's True/False verdict off the child's last stdout line.

    Output printed before the verdict is tolerated, but the verdict itself
    must be one of the two expected tokens. Comparing the whole of stdout
    against "True" would instead answer False for any unexpected output --
    silently turning the layering assertions into no-op passes, which is the
    one failure mode this file exists to prevent.
    """
    lines = stdout.strip().splitlines()
    verdict = lines[-1].strip() if lines else ""
    assert verdict in ("True", "False"), f"unexpected probe output: {stdout!r}"
    return verdict == "True"


def datamodel_loaded_by_importing(module: str) -> bool:
    """Whether importing `module` first also loads kiln_ai.datamodel."""
    return _verdict_from(assert_imports_cleanly(module).stdout)


def _is_type_checking_guard(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _dotted_names_imported(body: list[ast.stmt], package: str) -> Iterator[str]:
    """Yield every dotted name named by an import that runs when `body` does.

    Descends into module-scope `if` and `try` blocks, which execute at import
    time, but skips `if TYPE_CHECKING:` bodies and never enters function or
    class bodies -- imports there resolve after both modules exist, so they
    cannot cause a cycle.
    """
    for node in body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                # Relative: strip `level - 1` trailing segments off the
                # containing package, then append the explicit part.
                parts = package.split(".")
                base = ".".join(
                    parts[: len(parts) - node.level + 1]
                    + ([node.module] if node.module else [])
                )
            # `from a.b import c` may name either module a.b.c or an
            # attribute of a.b; yield both and let the module filter decide.
            yield base
            for alias in node.names:
                yield f"{base}.{alias.name}" if base else alias.name
        elif isinstance(node, ast.If):
            if not _is_type_checking_guard(node.test):
                yield from _dotted_names_imported(node.body, package)
            yield from _dotted_names_imported(node.orelse, package)
        elif isinstance(node, ast.Try):
            for block in (node.body, node.orelse, node.finalbody):
                yield from _dotted_names_imported(block, package)
            for handler in node.handlers:
                yield from _dotted_names_imported(handler.body, package)


def _is_module(dotted: str) -> bool:
    """Whether `dotted` names a real importable module under libs/core.

    Accepts packages as well as `.py` files. `kiln_ai.utils` is flat today,
    but a future `kiln_ai/utils/foo/__init__.py` must not silently drop out
    of the scan the way a subpackage would with a file-only check.
    """
    path = CORE_ROOT / Path(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def datamodel_source_files() -> list[Path]:
    """Every non-test source file in kiln_ai.datamodel, subpackages included."""
    return sorted(
        path
        for path in DATAMODEL_DIR.rglob("*.py")
        if not path.name.startswith("test_")
    )


def utils_modules_imported_by_datamodel() -> list[str]:
    """Every `kiln_ai.utils.*` module that `kiln_ai.datamodel` imports at
    module scope, across the package and its subpackages."""
    modules: set[str] = set()
    for source_file in datamodel_source_files():
        package = ".".join(source_file.relative_to(CORE_ROOT).parts[:-1])
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        modules.update(
            dotted
            for dotted in _dotted_names_imported(tree.body, package)
            if dotted.startswith(f"{UTILS_PACKAGE}.") and _is_module(dotted)
        )
    return sorted(modules)


def test_discovery_covers_the_modules_from_the_old_cycle():
    """Guards the parametrization below: a scan that quietly found nothing
    would make the layering test pass vacuously."""
    discovered = utils_modules_imported_by_datamodel()

    assert "kiln_ai.utils.open_ai_types" in discovered
    assert "kiln_ai.utils.usage" in discovered


def test_scan_reaches_datamodel_subpackages():
    """The scan must keep up with the package as it grows. A flat
    `datamodel/*.py` walk would silently stop covering subpackages, which is
    worse than no tripwire at all."""
    scanned = datamodel_source_files()

    assert any(path.parent != DATAMODEL_DIR for path in scanned), (
        "expected at least one datamodel subpackage to be scanned; if the "
        "subpackages are gone, confirm a recursive walk is still warranted"
    )


@pytest.mark.parametrize("module", utils_modules_imported_by_datamodel())
def test_datamodel_utils_dependency_does_not_import_datamodel(module: str):
    """kiln_ai.datamodel depends on these, so none of them may depend back on
    kiln_ai.datamodel at import time -- that is the cycle."""
    assert not datamodel_loaded_by_importing(module)


@pytest.mark.parametrize(
    "module",
    ["kiln_ai.datamodel", "kiln_ai.datamodel.usage", "kiln_ai.datamodel.task_run"],
)
def test_datamodel_module_imports_first_without_cycle(module: str):
    """The datamodel side must stay importable when it is the entry point.

    The subject here is the absence of an ImportError. There is deliberately
    no assertion on whether kiln_ai.datamodel loaded: importing any of these
    necessarily loads the parent package, so that check could never fail.
    """
    assert_imports_cleanly(module)


def dotted_names_in(source: str, package: str = "kiln_ai.datamodel") -> set[str]:
    return set(_dotted_names_imported(ast.parse(source).body, package))


@pytest.mark.parametrize(
    "source,expected",
    [
        pytest.param(
            "import kiln_ai.utils.usage",
            {"kiln_ai.utils.usage"},
            id="plain-import",
        ),
        pytest.param(
            "from kiln_ai.utils.usage import Usage",
            {"kiln_ai.utils.usage", "kiln_ai.utils.usage.Usage"},
            id="from-import-of-attribute",
        ),
        pytest.param(
            "from kiln_ai.utils import usage",
            {"kiln_ai.utils", "kiln_ai.utils.usage"},
            id="from-import-of-submodule",
        ),
        pytest.param(
            "from ..utils import usage",
            {"kiln_ai.utils", "kiln_ai.utils.usage"},
            id="relative-import",
        ),
        pytest.param(
            "if sys.platform == 'win32':\n    import kiln_ai.utils.usage",
            {"kiln_ai.utils.usage"},
            id="inside-module-scope-if",
        ),
        pytest.param(
            "try:\n    import kiln_ai.utils.usage\nexcept ImportError:\n"
            "    import kiln_ai.utils.config",
            {"kiln_ai.utils.usage", "kiln_ai.utils.config"},
            id="inside-try-and-except",
        ),
        pytest.param(
            "if TYPE_CHECKING:\n    import kiln_ai.utils.usage\nelse:\n"
            "    import kiln_ai.utils.config",
            {"kiln_ai.utils.config"},
            id="type-checking-body-skipped-but-else-kept",
        ),
        pytest.param(
            "def f():\n    import kiln_ai.utils.usage",
            set(),
            id="function-local-import-skipped",
        ),
    ],
)
def test_scan_sees_every_import_form_that_can_cause_a_cycle(
    source: str, expected: set[str]
):
    """The scan is the tripwire, so it has to recognise the forms a future
    import could arrive in -- not just the ones the package uses today."""
    assert dotted_names_in(source) == expected


def test_module_filter_drops_names_that_are_not_modules():
    """`from kiln_ai.utils.usage import Usage` yields a class name too; only
    the real module should survive into the parametrized layering test."""
    names = dotted_names_in("from kiln_ai.utils.usage import Usage")

    assert _is_module("kiln_ai.utils.usage")
    assert not _is_module("kiln_ai.utils.usage.Usage")
    assert {name for name in names if _is_module(name)} == {"kiln_ai.utils.usage"}


def test_module_filter_accepts_packages_not_just_files():
    """A subpackage is as importable as a module. A file-only check would drop
    a future `kiln_ai/utils/foo/` out of the layering parametrization without
    failing anything."""
    assert _is_module("kiln_ai.datamodel")  # a package directory
    assert not _is_module("kiln_ai.datamodel.no_such_module")


@pytest.mark.parametrize(
    "stdout,expected",
    [
        pytest.param("True\n", True, id="loaded"),
        pytest.param("False\n", False, id="not-loaded"),
        # The case that would otherwise read as "not loaded" and quietly
        # disarm the layering assertions.
        pytest.param("some notice\nTrue\n", True, id="noise-before-verdict"),
        pytest.param("some notice\nFalse\n", False, id="noise-before-false"),
    ],
)
def test_verdict_survives_unexpected_child_output(stdout: str, expected: bool):
    assert _verdict_from(stdout) is expected


@pytest.mark.parametrize("stdout", ["", "   ", "yes", "True is what we got"], ids=repr)
def test_verdict_refuses_to_guess_at_unrecognised_output(stdout: str):
    """Better to fail loudly than to answer False and let a real layering
    violation slip through unnoticed."""
    with pytest.raises(AssertionError, match="unexpected probe output"):
        _verdict_from(stdout)


def test_probe_reports_the_verdict_even_from_a_child_that_left_stdout_mid_line():
    """The probe prefixes its verdict with a newline so the parent can read it
    off the last stdout line whatever the child wrote first.

    That prefix is the contract `_verdict_from` relies on, and exercising it
    end to end also pins the choice of sys.stdout.write: the print builtin
    emits no such prefix, so a simplification back to it fails here rather
    than only in CI.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.stdout.write('noise'); {_REPORT_DATAMODEL_LOADED}",
        ],
        capture_output=True,
        text=True,
        timeout=_IMPORT_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "noise\nFalse"
    assert _verdict_from(result.stdout) is False


def test_assert_imports_cleanly_fails_when_the_import_raises():
    """Locks in that helper's assertion. Without it,
    test_datamodel_module_imports_first_without_cycle -- whose only subject is
    a clean import -- would pass vacuously."""
    with pytest.raises(AssertionError, match="first failed"):
        assert_imports_cleanly("kiln_ai.utils.no_such_module")
