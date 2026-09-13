from __future__ import annotations

import sys

import pytest

from .call import Call, build_chain, invoke
from .ctx import Ctx
from .errors import ArgumentError, ToolError, WorldBug

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


def call_for(instance, tool_name: str, /, **arguments) -> Call:
    return Call(tool_name, arguments, instance.world.tools[tool_name])


def test_chain_order_entry_exit(blank):
    order: list[str] = []

    def outer(ctx, call, next_handler):
        order.append("outer in")
        try:
            return next_handler(ctx, call)
        finally:
            order.append("outer out")

    def inner(ctx, call, next_handler):
        order.append("inner in")
        try:
            return next_handler(ctx, call)
        finally:
            order.append("inner out")

    chain = build_chain([outer, inner], lambda ctx, call: order.append("handler") or 7)
    assert chain(blank.ctx, call_for(blank, "add_item", name="x")) == 7
    assert order == ["outer in", "inner in", "handler", "inner out", "outer out"]


def test_middleware_short_circuits(blank):
    def refuse(ctx, call, next_handler):
        raise ToolError("refused", "not today")

    chain = build_chain([refuse], invoke)
    with pytest.raises(ToolError, match="not today"):
        chain(blank.ctx, call_for(blank, "add_item", name="x"))
    assert blank.db.one("SELECT id FROM items") is None


def test_with_arguments_ctx_call_identity_below(blank):
    seen: list[Ctx] = []

    def rewrite(ctx, call, next_handler):
        return next_handler(ctx, call.with_arguments(name="rewritten"))

    def observe(ctx, call, next_handler):
        seen.append(ctx)
        assert ctx.call is call
        return next_handler(ctx, call)

    chain = build_chain([rewrite, observe], invoke)
    original = call_for(blank, "add_item", name="original")
    chain(blank.ctx, original)
    assert seen[0].call is not None and seen[0].call.arguments["name"] == "rewritten"
    assert original.arguments["name"] == "original"
    assert blank.db.one("SELECT name FROM items")["name"] == "rewritten"


def test_argument_error_passes_through_chain(blank):
    seen: list[str] = []

    def watch(ctx, call, next_handler):
        try:
            return next_handler(ctx, call)
        except ArgumentError as e:
            seen.append(e.code)
            raise

    chain = build_chain([watch], invoke)
    with pytest.raises(ArgumentError):
        chain(blank.ctx, call_for(blank, "add_item", name=3))
    assert seen == ["invalid_arguments"]


def test_transaction_rolls_back_write_then_raise(toy_world, blank):
    @toy_world.tool
    def write_then_fail(ctx: Ctx, name: str) -> None:
        """Write, then fail."""
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('x', ?)", name)
        raise ToolError("boom", "boom")

    with pytest.raises(ToolError, match="boom"):
        invoke(blank.ctx, call_for(blank, "write_then_fail", name="x"))
    assert blank.db.one("SELECT id FROM items WHERE id = 'x'") is None


def test_transaction_false_keeps_write(toy_world, blank):
    @toy_world.tool(transaction=False)
    def write_then_fail_uncommitted(ctx: Ctx, name: str) -> None:
        """Write outside a transaction, then fail."""
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('y', ?)", name)
        raise ToolError("boom", "boom")

    with pytest.raises(ToolError):
        invoke(blank.ctx, call_for(blank, "write_then_fail_uncommitted", name="y"))
    assert blank.db.one("SELECT id FROM items WHERE id = 'y'") is not None


def test_unserialisable_result_rolls_back(toy_world, blank):
    @toy_world.tool
    def returns_object(ctx: Ctx) -> object:
        """Write, then return something that is not JSON."""
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('z', 'z')")
        return object()

    with pytest.raises(WorldBug, match="not JSON"):
        invoke(blank.ctx, call_for(blank, "returns_object"))
    assert blank.db.one("SELECT id FROM items WHERE id = 'z'") is None


def test_bytes_result_is_world_bug(toy_world, blank):
    @toy_world.tool
    def returns_bytes(ctx: Ctx) -> bytes:
        """Return bytes."""
        return b"binary"

    with pytest.raises(WorldBug, match="returned bytes"):
        invoke(blank.ctx, call_for(blank, "returns_bytes"))


def test_state_shared_across_calls_call_distinct(toy_world, blank):
    seen: list[tuple[int, str | None]] = []

    @toy_world.tool
    def count_calls(ctx: Ctx) -> int:
        """Count how often this instance has been called."""
        ctx.state["n"] = ctx.state.get("n", 0) + 1
        seen.append((ctx.state["n"], ctx.call.name if ctx.call else None))
        return ctx.state["n"]

    assert blank.call("count_calls") == 1
    assert blank.call("count_calls") == 2
    assert seen == [(1, "count_calls"), (2, "count_calls")]
    assert blank.ctx.call is None
