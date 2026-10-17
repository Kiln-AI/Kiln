import asyncio
import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import jsonschema

from kiln_ai.adapters.eval.trace_tools.v1.definitions import (
    PREVIEW_MESSAGES,
    READ_MESSAGE_TEXT,
    READ_MESSAGES,
    SEARCH_TRACE,
    TOOL_DEFINITIONS,
    TRACE_OVERVIEW,
    ToolDefinition,
    tool_definition,
)
from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.limits import (
    PREVIEW_CHARS_DEFAULT,
    READ_MAX_CHARS_DEFAULT,
    SEARCH_CONTEXT_DEFAULT,
    SEARCH_COUNT_DEFAULT,
    TEXT_MAX_CHARS_DEFAULT,
)
from kiln_ai.adapters.eval.trace_tools.v1.render import (
    DEFAULT_PARTS,
    PreviewArgs,
    ReadArgs,
    TextArgs,
    check_numbers_or_range,
    preview_messages,
    read_message_text,
    read_messages,
    render_overview,
    unknown_value_error,
)
from kiln_ai.adapters.eval.trace_tools.v1.search import SearchArgs, search_trace
from kiln_ai.adapters.eval.trace_tools.v1.view import PARTS, Part, TraceView
from kiln_ai.datamodel.tool_id import build_kiln_unmanaged_tool_id
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallResult,
    UnmanagedKilnTool,
)

__all__ = ["ToolArgs", "build_tools", "parse_args"]

ToolArgs = PreviewArgs | ReadArgs | TextArgs | SearchArgs
"""The parsed arguments of a trace tool, with defaults applied."""

_ArgsT = TypeVar("_ArgsT")


def parse_args(tool_name: str, kwargs: Mapping[str, Any]) -> ToolArgs | None:
    """Validate a trace tool's arguments and apply its defaults.

    Returns None for ``trace_overview``, which takes no arguments. Raises
    ``TraceToolUsageError`` when the arguments don't match the tool's schema,
    and ``ValueError`` for a name that isn't a v1 trace tool.
    """
    return _spec(tool_name).parse(kwargs)


def _validate(definition: ToolDefinition, kwargs: Mapping[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator(definition.parameters).validate(dict(kwargs))
    except jsonschema.ValidationError as e:
        location = "" if e.json_path == "$" else f" (at {e.json_path})"
        raise TraceToolUsageError(f"Invalid arguments: {e.message}{location}") from None


def _preview_args(kwargs: Mapping[str, Any]) -> PreviewArgs:
    return PreviewArgs(
        start=_optional_int(kwargs, "start"),
        end=_optional_int(kwargs, "end"),
        roles=_optional_roles(kwargs),
        preview_chars=_int(kwargs, "preview_chars", PREVIEW_CHARS_DEFAULT),
    )


def _read_args(kwargs: Mapping[str, Any]) -> ReadArgs:
    numbers = kwargs.get("numbers")
    args = ReadArgs(
        numbers=None if numbers is None else tuple(int(n) for n in numbers),
        start=_optional_int(kwargs, "start"),
        end=_optional_int(kwargs, "end"),
        roles=_optional_roles(kwargs),
        parts=_parts(kwargs),
        max_chars=_int(kwargs, "max_chars", READ_MAX_CHARS_DEFAULT),
    )
    check_numbers_or_range(args.numbers, args.start, args.end)
    return args


def _text_args(kwargs: Mapping[str, Any]) -> TextArgs:
    return TextArgs(
        number=int(kwargs["number"]),
        part=_part(kwargs.get("part", "content")),
        offset=_int(kwargs, "offset", 0),
        max_chars=_int(kwargs, "max_chars", TEXT_MAX_CHARS_DEFAULT),
    )


def _search_args(kwargs: Mapping[str, Any]) -> SearchArgs:
    return SearchArgs(
        pattern=kwargs["pattern"],
        regex=kwargs.get("regex", False),
        case_sensitive=kwargs.get("case_sensitive", False),
        roles=_optional_roles(kwargs),
        parts=_parts(kwargs),
        context_chars=_int(kwargs, "context_chars", SEARCH_CONTEXT_DEFAULT),
        start=_optional_int(kwargs, "start"),
        end=_optional_int(kwargs, "end"),
        count=_int(kwargs, "count", SEARCH_COUNT_DEFAULT),
        offset=_int(kwargs, "offset", 0),
    )


# JSON Schema counts 5.0 as an integer, so validated values can still be floats.
def _int(kwargs: Mapping[str, Any], key: str, default: int) -> int:
    return int(kwargs[key]) if key in kwargs else default


def _optional_int(kwargs: Mapping[str, Any], key: str) -> int | None:
    return int(kwargs[key]) if key in kwargs else None


def _optional_roles(kwargs: Mapping[str, Any]) -> tuple[str, ...] | None:
    roles = kwargs.get("roles")
    return None if roles is None else tuple(dict.fromkeys(roles))


def _parts(kwargs: Mapping[str, Any]) -> tuple[Part, ...]:
    parts = kwargs.get("parts")
    if parts is None:
        return DEFAULT_PARTS
    unique: dict[Part, None] = dict.fromkeys(_part(part) for part in parts)
    return tuple(unique)


def _part(value: Any) -> Part:
    for part in PARTS:
        if part == value:
            return part
    raise unknown_value_error("part", value, PARTS)


def _no_args(kwargs: Mapping[str, Any]) -> None:
    return None


def _overview(view: TraceView, args: None) -> str:
    return render_overview(view)


@dataclass(frozen=True)
class _ToolSpec(Generic[_ArgsT]):
    definition: ToolDefinition
    parse_valid: Callable[[Mapping[str, Any]], _ArgsT]
    """Builds the arguments from kwargs that already match the schema."""
    execute: Callable[[TraceView, _ArgsT], str]
    runs_in_thread: bool = False

    def parse(self, kwargs: Mapping[str, Any]) -> _ArgsT:
        _validate(self.definition, kwargs)
        return self.parse_valid(kwargs)

    def run(self, view: TraceView, kwargs: Mapping[str, Any]) -> str:
        return self.execute(view, self.parse(kwargs))


_SPECS: tuple[_ToolSpec[Any], ...] = (
    _ToolSpec(tool_definition(TRACE_OVERVIEW), _no_args, _overview),
    _ToolSpec(tool_definition(PREVIEW_MESSAGES), _preview_args, preview_messages),
    _ToolSpec(
        tool_definition(READ_MESSAGES), _read_args, read_messages, runs_in_thread=True
    ),
    _ToolSpec(tool_definition(READ_MESSAGE_TEXT), _text_args, read_message_text),
    _ToolSpec(
        tool_definition(SEARCH_TRACE), _search_args, search_trace, runs_in_thread=True
    ),
)


def _spec(tool_name: str) -> _ToolSpec[Any]:
    for spec in _SPECS:
        if spec.definition.name == tool_name:
            return spec
    raise ValueError(f"No v1 trace tool named {tool_name!r}.")


class _TraceTool(UnmanagedKilnTool):
    """A trace tool bound to one judged trace."""

    def __init__(self, view: TraceView, spec: _ToolSpec[Any]):
        super().__init__(
            tool_id=build_kiln_unmanaged_tool_id(f"trace_v1_{spec.definition.name}"),
            name=spec.definition.name,
            description=spec.definition.description,
            parameters_schema=copy.deepcopy(dict(spec.definition.parameters)),
        )
        self._view = view
        self._spec = spec

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        if self._spec.runs_in_thread:
            output = await asyncio.to_thread(self._spec.run, self._view, kwargs)
        else:
            output = self._spec.run(self._view, kwargs)
        return ToolCallResult(output=output)


def build_tools(view: TraceView) -> list[KilnToolInterface]:
    """The five v1 trace tools over ``view``, in their fixed order.

    Tool errors the judge can fix are raised as ``TraceToolUsageError``, which
    the model adapter returns to the model as an error result.
    """
    return [_TraceTool(view, _spec(definition.name)) for definition in TOOL_DEFINITIONS]
