"""The one argument every tool takes.

`Ctx` is the instance, seen from inside a tool: its database, its frozen clock, its seeded
id source, a scratch dict shared across the instance's calls, what it is a copy of, and the
call in flight. It is frozen; `with_call` makes the per-call copy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from .clock import Clock
from .db import Db
from .ids import Ids

if TYPE_CHECKING:  # avoids a cycle: call.py needs Ctx, Ctx only names Call
    from .call import Call


@dataclass(frozen=True)
class InstanceInfo:
    id: str
    fixture: str | None
    seed: bytes


@dataclass(frozen=True)
class Ctx:
    db: Db
    clock: Clock
    ids: Ids
    state: dict[str, Any]
    instance: InstanceInfo
    call: "Call | None" = None

    def with_call(self, call: "Call") -> "Ctx":
        return replace(self, call=call)
