"""Pytest plugin: the ``kiln`` test shim.

Auto-discovered via the ``pytest11`` entry point (see
``libs/core/pyproject.toml``). At plugin load it installs the same synthetic
``kiln`` / ``kiln.tools`` / ``kiln.async_tools`` surface the sandbox installs —
built from :mod:`kiln_ai.sandbox.tools_surface` — into ``sys.modules`` *before*
test modules are imported, so a top-level ``from kiln import tools`` in an
author's ``tool.py`` resolves during collection. The ``kiln_tools`` fixture then
lets authors stub each tool's reply and inspect calls.

This is a test-support surface only: it never spawns a subprocess, never calls a
real tool, and is never loaded inside the sandbox (the sandbox installs its own
real IPC bridge in the child process).
"""

from __future__ import annotations

from typing import Iterator

import pytest

from kiln_ai.sandbox.tools_surface import install_tools_modules_for_bridge
from kiln_ai.tool_testing.fake_bridge import FakeToolBridge

# One process-global fake bridge. The synthetic modules installed at plugin load
# capture this instance; the ``kiln_tools`` fixture resets it per test. Each
# pytest-xdist worker is a separate process, so this never crosses workers.
_bridge = FakeToolBridge()


def pytest_configure(config: pytest.Config) -> None:
    """Install the synthetic ``kiln`` modules before test collection.

    ``pytest_configure`` runs after plugins load and before test modules are
    imported, so ``from kiln import tools`` at the top of a ``tool.py`` resolves
    during collection. A fixture alone would be too late.
    """
    install_tools_modules_for_bridge(_bridge)


@pytest.fixture
def kiln_tools() -> Iterator[FakeToolBridge]:
    """Function-scoped access to the fake tool bridge, auto-reset each test.

    Use ``kiln_tools.set(name, reply)`` / ``kiln_tools.set_error(name, exc)`` to
    stub tool replies, and inspect ``kiln_tools.calls`` for assertions. The same
    registry backs both ``kiln.tools`` (sync) and ``kiln.async_tools`` (async).
    """
    _bridge.reset()
    try:
        yield _bridge
    finally:
        _bridge.reset()
