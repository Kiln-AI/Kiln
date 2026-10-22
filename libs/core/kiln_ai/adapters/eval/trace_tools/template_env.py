from collections.abc import Callable, Mapping
from typing import Any

from jinja2 import Environment

from kiln_ai.adapters.eval.trace_tools.toolset import TraceToolset, TraceViewProtocol
from kiln_ai.utils.jinja_engine import JinjaExtractionError, template_env_with_filters


def judge_template_env(
    toolset: TraceToolset,
    trace: list[dict[str, Any]] | None,
    view: TraceViewProtocol | None,
) -> Environment:
    """The template environment for one LLM judge prompt, with ``trace_overview``
    bound to ``toolset``'s overview.

    ``trace`` is the judged trace, and ``view`` its view if already built for the
    judge's tools. When ``view`` is None and the template applies the filter to
    ``trace``, the view is built once on first use.
    """
    return template_env_with_filters(
        {"trace_overview": _trace_overview_filter(toolset, trace, view)}
    )


def _trace_overview_filter(
    toolset: TraceToolset,
    trace: list[dict[str, Any]] | None,
    view: TraceViewProtocol | None,
) -> Callable[[Any], str]:
    judged_view = view

    def trace_overview(value: Any) -> str:
        nonlocal judged_view
        if trace is not None and value is trace:
            if judged_view is None:
                judged_view = toolset.build_view(trace)
            return toolset.render_overview(judged_view)
        return toolset.render_overview(toolset.build_view(_message_list(value)))

    return trace_overview


def _message_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise JinjaExtractionError(
            f"trace_overview filter expected a list of messages, got {type(value).__name__}"
        )
    for index, message in enumerate(value):
        if not isinstance(message, dict):
            raise JinjaExtractionError(
                f"trace_overview filter expected a list of messages, but message "
                f"{index} is {type(message).__name__}, not a dict"
            )
    return value
