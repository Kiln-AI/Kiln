"""A toy world the shim's own tests share.

Two tracked tables — one with a single primary key, one with a composite — plus an untracked
counter, so a test can exercise the changes diff on every shape without inventing a schema.
"""

from __future__ import annotations

import pytest

from .ctx import Ctx
from .errors import ToolError
from .fixtures import Fixture
from .world import World

FIXED_NOW = "2026-03-04T05:06:07.008Z"

SEEN: list[str] = []
"""Tool names the toy world's middleware has seen, reset by each `build_toy_world`."""

TOY_SCHEMA = """
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    payload BLOB
) STRICT;

CREATE TABLE tags (
    item_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id, tag)
) STRICT;

CREATE TABLE counters (
    name TEXT PRIMARY KEY,
    n INTEGER NOT NULL
) STRICT;
"""


def build_toy_world(tmp_path, *, with_hook: bool = False, **kwargs) -> World:
    world = World(
        "toy",
        version="1.0.0",
        schema=TOY_SCHEMA,
        fixtures_dir=kwargs.pop("fixtures_dir", tmp_path / "fixtures"),
        work_dir=kwargs.pop("work_dir", tmp_path / "work"),
        untracked_tables=("counters",),
        **kwargs,
    )
    SEEN.clear()

    @world.tool
    def add_item(ctx: Ctx, name: str, note: str | None = None) -> dict:
        """Add an item to the list."""
        item_id = ctx.ids.uuid()
        ctx.db.execute(
            "INSERT INTO items (id, name, note) VALUES (?, ?, ?)", item_id, name, note
        )
        ctx.db.execute(
            "INSERT INTO counters (name, n) VALUES ('adds', 1) "
            "ON CONFLICT(name) DO UPDATE SET n = n + 1"
        )
        return {"id": item_id, "name": name}

    @world.tool
    def tag_item(ctx: Ctx, item_id: str, tag: str, weight: int = 1) -> dict:
        """Tag an item."""
        if ctx.db.one("SELECT id FROM items WHERE id = ?", item_id) is None:
            raise ToolError("not_found", f"no item {item_id}", {"id": item_id})
        ctx.db.execute(
            "INSERT INTO tags (item_id, tag, weight) VALUES (?, ?, ?)",
            item_id,
            tag,
            weight,
        )
        return {"item_id": item_id, "tag": tag}

    @world.tool
    def finish_item(ctx: Ctx, item_id: str) -> dict:
        """Mark an item done."""
        if not ctx.db.execute(
            "UPDATE items SET done = 1 WHERE id = ?", item_id
        ).rowcount:
            raise ToolError("not_found", f"no item {item_id}", {"id": item_id})
        return {"id": item_id, "done": True}

    @world.middleware
    def record(ctx: Ctx, call, next_handler):
        SEEN.append(call.name)
        return next_handler(ctx, call)

    if with_hook:

        @world.instance_startup
        def seed(ctx: Ctx, *, owner: str = "nobody") -> None:
            ctx.db.execute(
                "INSERT INTO items (id, name, note) VALUES ('seeded', 'seeded', ?)",
                owner,
            )

    return world


@pytest.fixture
def seen() -> list[str]:
    return SEEN


@pytest.fixture
def toy_world(tmp_path) -> World:
    return build_toy_world(tmp_path)


@pytest.fixture
def blank(toy_world):
    instance = toy_world.instance(None, now=FIXED_NOW)
    try:
        yield instance
    finally:
        instance.destroy()


@pytest.fixture
def frozen(toy_world) -> Fixture:
    """A fixture with two items and one tag, frozen at `FIXED_NOW`."""
    instance = toy_world.instance(None, now=FIXED_NOW)
    try:
        with instance.bulk() as ctx:
            ctx.db.execute(
                "INSERT INTO items (id, name, note) VALUES ('i1', 'first', NULL)"
            )
            ctx.db.execute(
                "INSERT INTO items (id, name, note) VALUES ('i2', 'second', 'noted')"
            )
            ctx.db.execute("INSERT INTO tags (item_id, tag) VALUES ('i1', 'red')")
            ctx.db.execute("INSERT INTO counters (name, n) VALUES ('adds', 0)")
        return instance.freeze("base", "two items")
    finally:
        instance.destroy()
