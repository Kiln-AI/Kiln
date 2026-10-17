from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from kiln_ai.tools.base_tool import KilnToolInterface


class TraceViewProtocol(Protocol):
    """A judged trace parsed by one toolset version. Opaque outside that version:
    only the toolset that built it can read it."""


class TraceToolset(Protocol):
    """One frozen version of the trace tools and of the ``trace_overview`` output."""

    @property
    def version(self) -> int:
        """The version number a judge records to get this toolset back, such as 1."""
        ...

    def build_view(self, trace: Sequence[Mapping[str, Any]]) -> TraceViewProtocol:
        """Parse a judged trace once, for this version's overview and tools.

        CPU-bound on large traces: call it off the event loop."""
        ...

    def render_overview(self, view: TraceViewProtocol) -> str:
        """The ``trace_overview`` text for a view this toolset built."""
        ...

    def build_tools(self, view: TraceViewProtocol) -> list[KilnToolInterface]:
        """The judge's tools over ``view``, in their fixed order."""
        ...

    @property
    def judge_thinking_instruction(self) -> str:
        """Sent after the judge's rendered prompt in its first turn, which has the
        tools and no score format: investigate the trace and describe the decision,
        because the formatted scores are asked for in a final turn of their own."""
        ...


class UnsupportedTraceToolsetVersion(Exception):
    """A judge asked for a trace toolset version this build of Kiln doesn't have."""

    def __init__(self, version: int):
        super().__init__(f"Unsupported trace toolset version: {version}")
        self.version = version


def trace_toolset(version: int) -> TraceToolset:
    """The trace toolset for a judge's recorded version.

    Raises ``UnsupportedTraceToolsetVersion`` for versions newer than this build.
    """
    match version:
        case 1:
            from kiln_ai.adapters.eval.trace_tools.v1 import TOOLSET_V1

            return TOOLSET_V1
        case _:
            raise UnsupportedTraceToolsetVersion(version)
