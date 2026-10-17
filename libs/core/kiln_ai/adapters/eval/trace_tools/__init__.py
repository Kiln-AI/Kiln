"""Trace tools: read-only tools an LLM judge calls to read the trace it judges,
and the ``trace_overview`` template filter.

Each toolset version lives in its own frozen subpackage (``v1``). A judge records
the version it was created with, and ``trace_toolset(version)`` returns it.
"""

from kiln_ai.adapters.eval.trace_tools.template_env import judge_template_env
from kiln_ai.adapters.eval.trace_tools.toolset import (
    TraceToolset,
    TraceViewProtocol,
    UnsupportedTraceToolsetVersion,
    trace_toolset,
)

__all__ = [
    "TraceToolset",
    "TraceViewProtocol",
    "UnsupportedTraceToolsetVersion",
    "judge_template_env",
    "trace_toolset",
]
