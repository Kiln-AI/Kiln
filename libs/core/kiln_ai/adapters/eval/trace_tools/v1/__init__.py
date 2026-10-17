"""Trace toolset v1: read-only tools an LLM judge uses to read the trace it judges.

Frozen once released. Change it only to fix wrong output (a crash, a wrong
count, a wrong address); anything else ships as a new version, which starts as
a copy of this package. Nothing here imports from another version or from the
version-independent ``trace_tools`` modules, so they can't change it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from kiln_ai.adapters.eval.trace_tools.v1.render import render_overview
from kiln_ai.adapters.eval.trace_tools.v1.tools import build_tools
from kiln_ai.adapters.eval.trace_tools.v1.view import TraceView, build_view
from kiln_ai.tools.base_tool import KilnToolInterface

__all__ = ["TOOLSET_V1", "TraceToolsetV1"]


@dataclass(frozen=True)
class TraceToolsetV1:
    """Trace toolset version 1. Use the ``TOOLSET_V1`` instance."""

    @property
    def version(self) -> int:
        """The toolset version a judge records: 1."""
        return 1

    def build_view(self, trace: Sequence[Mapping[str, Any]]) -> TraceView:
        """Parse a judged trace once, for this version's overview and tools.

        CPU-bound on large traces: call it off the event loop."""
        return build_view(trace)

    def render_overview(self, view: object) -> str:
        """The ``trace_overview`` text for a view from ``build_view``."""
        return render_overview(_own_view(view))

    def build_tools(self, view: object) -> list[KilnToolInterface]:
        """The five trace tools over a view from ``build_view``, in their fixed order."""
        return build_tools(_own_view(view))


def _own_view(view: object) -> TraceView:
    if not isinstance(view, TraceView):
        raise TypeError(
            f"Trace toolset v1 needs a view built by its own build_view, got {type(view).__name__}."
        )
    return view


TOOLSET_V1 = TraceToolsetV1()
"""The trace toolset for judges that record ``trace_toolset_version=1``."""
