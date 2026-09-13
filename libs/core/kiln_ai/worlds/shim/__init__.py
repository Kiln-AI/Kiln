"""An interim runtime for Kiln worlds: the authoring surface a world package imports.

This is a deliberately throwaway stand-in for Seahaven, copying its surface so a world
written here moves there by changing one dependency. It gives a world a schema, tools, a
per-instance SQLite database with a frozen clock and seeded ids, fixtures that freeze and
verify, a net-changes diff, control tools for graders, and the OpenEnv wire server Kiln
connects to.

    from kiln_ai.worlds.shim import World, Ctx

    world = World("helpdesk", version="1", schema=DDL)

    @world.tool
    def close_ticket(ctx: Ctx, ticket_id: str) -> dict:
        "Close a ticket."
        ctx.db.execute("UPDATE tickets SET closed_at = datetime('now') WHERE id = ?", ticket_id)
        return {"id": ticket_id}

The exception names keep Seahaven's spelling on purpose: a world's `except SeahavenError`
survives the swap.
"""

from __future__ import annotations

from . import (
    call,
    changes,
    clock,
    conformance,
    control,
    ctx,
    db,
    errors,
    fixtures,
    ids,
    instances,
    tool,
    version,
    world,
)
from .call import Call
from .changes import Change
from .clock import Clock
from .ctx import Ctx
from .db import Db
from .errors import (
    ArgumentError,
    DbError,
    SeahavenError,
    ToolError,
    UnknownTool,
    WorldBug,
    WorldGap,
)
from .fixtures import Fixture, FixtureMeta
from .ids import Ids
from .instances import Instance
from .tool import Tool
from .world import World, sql_files

__all__ = [
    "ArgumentError",
    "Call",
    "Change",
    "Clock",
    "Ctx",
    "Db",
    "DbError",
    "Fixture",
    "FixtureMeta",
    "Ids",
    "Instance",
    "SeahavenError",
    "Tool",
    "ToolError",
    "UnknownTool",
    "World",
    "WorldBug",
    "WorldGap",
    "call",
    "changes",
    "clock",
    "conformance",
    "control",
    "ctx",
    "db",
    "errors",
    "fixtures",
    "ids",
    "instances",
    "sql_files",
    "tool",
    "version",
    "world",
]
