from __future__ import annotations

import sys
from datetime import date, datetime, time
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional

import pytest
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .ctx import Ctx
from .errors import ArgumentError, WorldBug
from .tool import Tool

if TYPE_CHECKING:
    from decimal import Decimal

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


class Colour(Enum):
    RED = "red"


class Nested(BaseModel):
    a: int


class NestedDict(TypedDict):
    a: int


class Opaque:
    """A type pydantic has no schema for."""


@pytest.mark.parametrize(
    "annotation, value",
    [
        (str, "x"),
        (int, 3),
        (float, 1.5),
        (bool, True),
        (Optional[str], None),
        (list[str], ["a", "b"]),
        (dict[str, int], {"a": 1}),
        (Literal["a", "b"], "b"),
        (Nested, {"a": 1}),
        (NestedDict, {"a": 1}),
        (Annotated[int, Field(ge=0)], 4),
    ],
)
def test_argument_models_parametrized(annotation, value):
    def sample(ctx: Ctx, thing) -> dict:
        """Sample."""
        return {"thing": thing}

    sample.__annotations__["thing"] = annotation
    tool = Tool.from_function(sample)
    validated = tool.validate({"thing": value})
    assert "thing" in validated
    assert tool.schema["properties"]["thing"]


@pytest.mark.parametrize(
    "annotation",
    [
        datetime,
        date,
        time,
        Colour,
        Optional[datetime],
        datetime | None,
        list[datetime],
        dict[str, date],
        Optional[Colour],
        list[list[time]],
        Annotated[Optional[datetime], Field(description="nested inside Annotated")],
    ],
)
def test_rejects_enum_datetime_date_time(annotation):
    """The refusal has to see through Optional, unions and containers: a strict model built
    over `Optional[datetime]` refuses every JSON value a client could send, so accepting one
    at registration hands the agent a tool it can never call."""

    def sample(ctx: Ctx, when) -> None: ...

    sample.__annotations__["when"] = annotation
    with pytest.raises(WorldBug, match="argument 'when'"):
        Tool.from_function(sample, name="sample")


@pytest.mark.parametrize("default", [[], {}, set()])
def test_rejects_mutable_default(default):
    def sample(ctx: Ctx, things: list[str] = default) -> None: ...

    with pytest.raises(WorldBug, match="mutable default"):
        Tool.from_function(sample, name="sample")


def test_rejects_missing_annotation_varargs_async_generator():
    def unannotated(ctx: Ctx, thing) -> None: ...

    with pytest.raises(WorldBug, match="needs an annotation"):
        Tool.from_function(unannotated)

    def varargs(ctx: Ctx, *things: str) -> None: ...

    with pytest.raises(WorldBug, match=r"\*args"):
        Tool.from_function(varargs)

    def kwargs(ctx: Ctx, **things: str) -> None: ...

    with pytest.raises(WorldBug, match=r"\*\*kwargs"):
        Tool.from_function(kwargs)

    def positional_only(ctx: Ctx, thing: str, /) -> None: ...

    with pytest.raises(WorldBug, match="positional-only"):
        Tool.from_function(positional_only)

    async def coroutine(ctx: Ctx) -> None: ...

    with pytest.raises(WorldBug, match="async"):
        Tool.from_function(coroutine)

    def generator(ctx: Ctx):
        yield 1

    with pytest.raises(WorldBug, match="generator"):
        Tool.from_function(generator)

    def no_arguments() -> None: ...

    with pytest.raises(WorldBug, match="the first one is the context"):
        Tool.from_function(no_arguments)

    def wrong_context(ctx: str) -> None: ...

    with pytest.raises(WorldBug, match="it is a Ctx"):
        Tool.from_function(wrong_context)

    def keyword_context(*, ctx: Ctx) -> None: ...

    with pytest.raises(WorldBug, match="first positional argument"):
        Tool.from_function(keyword_context)


def test_rejects_type_checking_only_name():
    def sample(ctx: Ctx, amount: Decimal) -> None: ...

    with pytest.raises(WorldBug, match="TYPE_CHECKING") as caught:
        Tool.from_function(sample)
    assert "Decimal" in str(caught.value)


def test_alias_on_wire_python_name_in_call():
    def sample(ctx: Ctx, item_id: Annotated[str, Field(alias="itemId")]) -> str:
        """Sample."""
        return item_id

    tool = Tool.from_function(sample)
    assert "itemId" in tool.schema["properties"]
    assert tool.validate({"itemId": "abc"}) == {"item_id": "abc"}
    with pytest.raises(ArgumentError):
        tool.validate({"item_id": "abc"})


def test_schema_no_title_additional_properties_false_docstring_description():
    def sample(ctx: Ctx, name: str, nested: Nested) -> None:
        """First line.

        Second line."""

    tool = Tool.from_function(sample)
    assert "title" not in tool.schema
    assert tool.schema["additionalProperties"] is False
    assert tool.schema["required"] == ["name", "nested"]
    assert "$defs" in tool.schema
    assert tool.description == "First line.\n\nSecond line."
    assert (
        Tool.from_function(sample, description="Explicit.").description == "Explicit."
    )

    def undocumented(ctx: Ctx) -> None: ...

    assert Tool.from_function(undocumented).description == ""


def test_strict_refuses_coercion_and_field_strict_false_relaxes_one():
    def sample(
        ctx: Ctx, strict_count: int, loose_count: Annotated[int, Field(strict=False)]
    ) -> None: ...

    tool = Tool.from_function(sample)
    assert tool.validate({"strict_count": 1, "loose_count": "2"}) == {
        "strict_count": 1,
        "loose_count": 2,
    }
    with pytest.raises(ArgumentError):
        tool.validate({"strict_count": "1", "loose_count": 2})


def test_validate_violations_list_all_three():
    def sample(ctx: Ctx, a: str, b: int, c: bool) -> None: ...

    tool = Tool.from_function(sample)
    with pytest.raises(ArgumentError) as caught:
        tool.validate({"a": 1, "b": "two"})
    paths = {violation["path"] for violation in caught.value.violations}
    assert paths == {"a", "b", "c"}
    assert all(
        set(violation) == {"path", "message", "type"}
        for violation in caught.value.violations
    )
    assert caught.value.tool == "sample"

    with pytest.raises(ArgumentError, match=r"extra_forbidden|Extra inputs"):
        tool.validate({"a": "x", "b": 1, "c": True, "d": 1})


def test_listing_exact_keys():
    def sample(ctx: Ctx) -> None:
        """Sample."""

    listing = Tool.from_function(sample).listing()
    assert set(listing) == {"name", "description", "input_schema"}
    assert listing["name"] == "sample"


def test_pydantic_failure_prefixed_with_tool_and_argument():
    """A type pydantic cannot describe fails at registration, naming the argument."""

    def sample(ctx: Ctx, ok: str, broken: Opaque) -> None: ...

    with pytest.raises(WorldBug, match="tool 'sample' argument 'broken'") as caught:
        Tool.from_function(sample, name="sample")
    assert "Opaque" in str(caught.value)


def test_name_override_and_transaction_flag():
    def sample(ctx: Ctx) -> None:
        """Sample."""

    tool = Tool.from_function(sample, name="renamed", transaction=False)
    assert (
        tool.name == "renamed" and tool.transaction is False and tool.control is False
    )
    assert tool.params.__name__ == "renamedArguments"


def test_no_argument_tool_schema_is_empty_object():
    def sample(ctx: Ctx) -> None:
        """Sample."""

    tool = Tool.from_function(sample)
    assert tool.schema["type"] == "object"
    assert tool.schema["properties"] == {}
    assert tool.validate({}) == {}
    with pytest.raises(ArgumentError):
        tool.validate({"surprise": 1})


def test_any_annotation_is_allowed():
    def sample(ctx: Ctx, payload: Any) -> None:
        """Sample."""

    assert Tool.from_function(sample).validate({"payload": [1, "x"]}) == {
        "payload": [1, "x"]
    }
