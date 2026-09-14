"""Created ids, mapped by creation order.

Replaying a recorded episode against the world mints new ids: the n-th create call in the
recording and the n-th create call in the replay are the same act, and everything the
episode does afterwards refers to whichever id its own system handed out. The map is the
translation: arguments are rewritten into world-id space before the call, results are
rewritten back into recorded-id space before the comparison, so nothing downstream has to
know an id was substituted.

Which tools create is the world's business, not this module's: `create_tools` is passed in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from pydantic import JsonValue

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class IdMapConflict(ValueError):
    """One recorded id was mapped to two different replayed ids, or the reverse. The
    creation-order assumption has broken down and the episode's results cannot be trusted."""


def created_id(
    tool_name: str, result: JsonValue, create_tools: frozenset[str]
) -> str | None:
    """The id a create call minted, or None when this call does not create one."""
    if tool_name not in create_tools or not isinstance(result, dict):
        return None
    value = result.get("id")
    return value if isinstance(value, str) and value else None


class IdMap:
    """Recorded id <-> replayed id, for one episode."""

    def __init__(self, create_tools: frozenset[str]) -> None:
        self.create_tools = create_tools
        self._to_world: dict[str, str] = {}
        self._to_recorded: dict[str, str] = {}

    def record(self, recorded_id: str, replayed_id: str) -> None:
        existing = self._to_world.get(recorded_id)
        if existing is not None and existing != replayed_id:
            raise IdMapConflict(
                f"recorded id {recorded_id} already maps to {existing}, not {replayed_id}"
            )
        reverse = self._to_recorded.get(replayed_id)
        if reverse is not None and reverse != recorded_id:
            raise IdMapConflict(
                f"replayed id {replayed_id} already maps back to {reverse}, not {recorded_id}"
            )
        self._to_world[recorded_id] = replayed_id
        self._to_recorded[replayed_id] = recorded_id

    def to_world(self, value: JsonValue) -> JsonValue:
        return _rewrite(value, self._to_world)

    def to_recorded(self, value: JsonValue) -> JsonValue:
        return _rewrite(value, self._to_recorded)

    def unknown_ids(self, value: JsonValue, known: frozenset[str]) -> list[str]:
        """Id-shaped strings in `value` that neither came with the fixture nor were
        created during this episode: the episode is referring to something the replay
        cannot have. Reported, never fatal."""
        found: list[str] = []
        for candidate in id_strings(value):
            if candidate in known or candidate in self._to_world:
                continue
            if candidate in self._to_recorded:
                continue
            if candidate not in found:
                found.append(candidate)
        return found

    @property
    def pairs(self) -> list[tuple[str, str]]:
        return list(self._to_world.items())


def id_strings(value: JsonValue) -> list[str]:
    """Every UUID-shaped string in a value, in traversal order, deduplicated."""
    found: list[str] = []
    _collect(value, found)
    return found


def _collect(value: Any, found: list[str]) -> None:
    if isinstance(value, str):
        if _UUID.match(value) and value not in found:
            found.append(value)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect(item, found)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect(item, found)


def _rewrite(value: JsonValue, mapping: dict[str, str]) -> JsonValue:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, dict):
        return {key: _rewrite(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite(item, mapping) for item in value]
    return value


def known_ids(values: Iterable[JsonValue]) -> frozenset[str]:
    """The id-shaped strings of a fixture export, for `unknown_ids`."""
    found: set[str] = set()
    for value in values:
        found.update(id_strings(value))
    return frozenset(found)
