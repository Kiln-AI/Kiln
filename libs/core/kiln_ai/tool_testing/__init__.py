"""The ``kiln`` test shim — a pytest plugin for testing code tools.

Shipped with ``kiln_ai`` and auto-discovered via the ``pytest11`` entry point
(``kiln_ai.tool_testing.plugin``). It installs the synthetic ``kiln`` /
``kiln.tools`` / ``kiln.async_tools`` surface so an author's ``tool.py`` (which
does ``from kiln import tools``) imports cleanly under pytest, and provides the
``kiln_tools`` fixture for stubbing tool replies and inspecting calls.

See ``plugin.py`` for the fixture and :class:`FakeToolBridge` for the registry.
"""

from kiln_ai.tool_testing.fake_bridge import FakeToolBridge, RecordedToolCall

__all__ = ["FakeToolBridge", "RecordedToolCall"]
