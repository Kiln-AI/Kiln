"""Turning a plain Python function into a tool an agent can call.

`Tool.from_function` reads the signature, builds a strict pydantic model from the arguments
and derives the JSON schema the agent sees. Everything it can refuse, it refuses at
registration time as a `WorldBug`: an `async def`, a missing annotation, a `datetime`
argument (which would make the wire format ambiguous — use a `str` with a pattern, or a
`Literal`), a mutable default, an annotation that only exists under `TYPE_CHECKING`. A
world that imports cleanly has no tool that can surprise an agent at call time.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Annotated, Any, Callable, Iterator, Mapping, get_args, get_origin

import pydantic
from pydantic import ConfigDict, ValidationError

from .ctx import Ctx
from .errors import ArgumentError, WorldBug

_FORBIDDEN_ANNOTATIONS: tuple[type, ...] = (datetime, date, time)


def _describe(annotation: Any) -> str:
    return getattr(annotation, "__name__", None) or repr(annotation)


def _annotation_parts(annotation: Any) -> Iterator[Any]:
    """The annotation and everything nested inside it.

    Looking only at the outermost type is not enough: `Optional[datetime]`, `datetime | None`
    and `list[datetime]` are generic aliases rather than types, so a top-level check waves
    them through. The model is then built with `strict=True`, which refuses the JSON string
    a wire client has to send — a registration-time bug turned into a tool the agent can
    never successfully call.
    """
    if get_origin(annotation) is Annotated:
        # Only the type travels; the rest is `Field(...)` metadata.
        arguments = get_args(annotation)
        if arguments:
            yield from _annotation_parts(arguments[0])
        return
    yield annotation
    for argument in get_args(annotation):
        yield from _annotation_parts(argument)


def _forbidden_reason(annotation: Any) -> str | None:
    for base in _annotation_parts(annotation):
        if not isinstance(base, type):
            continue
        if base in _FORBIDDEN_ANNOTATIONS:
            return (
                f"'{_describe(base)}' has no unambiguous wire form; use a str with a "
                "pattern, or a Literal"
            )
        if issubclass(base, Enum):
            return (
                f"enum '{_describe(base)}' does not survive the wire; use a Literal of "
                "its values"
            )
    return None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    params: type[pydantic.BaseModel]
    schema: dict[str, Any]
    transaction: bool = True
    control: bool = False

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        transaction: bool = True,
    ) -> "Tool":
        tool_name = name or getattr(fn, "__name__", None) or ""
        if not tool_name:
            raise WorldBug("a tool needs a name; pass name= for a callable without one")
        if inspect.iscoroutinefunction(fn):
            raise WorldBug(f"tool '{tool_name}' is async; tools are plain functions")
        if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
            raise WorldBug(
                f"tool '{tool_name}' is a generator function; tools return a value"
            )
        try:
            signature = inspect.signature(fn, eval_str=True)
        except NameError as e:
            raise WorldBug(
                f"tool '{tool_name}' annotates an argument with a name that only exists "
                f"under TYPE_CHECKING: {e}"
            ) from e

        parameters = list(signature.parameters.values())
        if not parameters:
            raise WorldBug(
                f"tool '{tool_name}' takes no arguments; the first one is the context"
            )
        first = parameters[0]
        if first.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            raise WorldBug(
                f"tool '{tool_name}' must take the context as its first positional argument"
            )
        if (
            first.annotation is not inspect.Parameter.empty
            and first.annotation is not Ctx
        ):
            raise WorldBug(
                f"tool '{tool_name}' annotates its context argument as "
                f"'{_describe(first.annotation)}'; it is a Ctx"
            )

        fields: dict[str, tuple[Any, Any]] = {}
        for parameter in parameters[1:]:
            _check_argument(tool_name, parameter)
            default = (
                ...
                if parameter.default is inspect.Parameter.empty
                else parameter.default
            )
            fields[parameter.name] = (parameter.annotation, default)

        params, schema = _build_model(tool_name, fields)
        schema.pop("title", None)
        if schema.get("additionalProperties") is not False:
            raise WorldBug(
                f"tool '{tool_name}' built a schema that accepts extra properties"
            )
        return cls(
            name=tool_name,
            description=description
            if description is not None
            else (inspect.getdoc(fn) or ""),
            fn=fn,
            params=params,
            schema=schema,
            transaction=transaction,
        )

    def validate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            model = self.params.model_validate(dict(arguments))
        except ValidationError as e:
            raise ArgumentError(self.name, _violations(e)) from e
        return {field: getattr(model, field) for field in type(model).model_fields}

    def listing(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }


def _check_argument(tool_name: str, parameter: inspect.Parameter) -> None:
    where = f"tool '{tool_name}' argument '{parameter.name}'"
    if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
        raise WorldBug(f"{where}: *args has no wire form")
    if parameter.kind is inspect.Parameter.VAR_KEYWORD:
        raise WorldBug(f"{where}: **kwargs has no wire form")
    if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
        raise WorldBug(
            f"{where}: arguments arrive by name, so it cannot be positional-only"
        )
    if parameter.annotation is inspect.Parameter.empty:
        raise WorldBug(f"{where}: every argument needs an annotation")
    reason = _forbidden_reason(parameter.annotation)
    if reason is not None:
        raise WorldBug(f"{where}: {reason}")
    if isinstance(parameter.default, (list, dict, set)):
        raise WorldBug(
            f"{where}: a mutable default is shared between calls; use None or a tuple"
        )


def _build_model(
    tool_name: str, fields: Mapping[str, tuple[Any, Any]]
) -> tuple[type[pydantic.BaseModel], dict[str, Any]]:
    """The arguments model and its JSON schema, or a `WorldBug` naming the argument at fault.

    An unresolvable annotation only fails when pydantic builds the schema, so both steps run
    together and, on failure, one field at a time.
    """
    try:
        model = _model(tool_name, fields)
        return model, model.model_json_schema(mode="validation")
    except Exception as whole:
        for argument, spec in fields.items():
            try:
                _model(tool_name, {argument: spec}).model_json_schema(mode="validation")
            except Exception as one:
                raise WorldBug(
                    f"tool '{tool_name}' argument '{argument}': {one}"
                ) from one
        raise WorldBug(f"tool '{tool_name}': {whole}") from whole


def _model(
    tool_name: str, fields: Mapping[str, tuple[Any, Any]]
) -> type[pydantic.BaseModel]:
    return pydantic.create_model(
        f"{tool_name}Arguments",
        __config__=ConfigDict(extra="forbid", strict=True),
        **dict(fields),
    )


def _violations(error: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "path": ".".join(str(part) for part in item["loc"]),
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors()
    ]
