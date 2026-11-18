"""The reset arguments an OpenEnv server publishes, as text a planning model can read.

A server's reset schema (Pydantic's `model_json_schema()` of its reset request) says which
starting states it offers, and its owner's descriptions say what each one holds. Kiln adds no
notes of its own: the descriptions are the brief. Nothing here looks for an argument by name,
since every server names its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import JsonValue

OPENENV_RESET_KEYS = frozenset({"seed", "episode_id"})
"""Reset arguments OpenEnv itself defines. They pick no starting state, so they are left out."""

MAX_ARGUMENT_DEPTH = 4
"""How many levels of nested object arguments are walked; deeper ones are listed as a leaf."""

_LOCAL_REF_PREFIX = "#/$defs/"

RESET_ARGUMENTS_FRAMING = """## The system the agent works on

The agent's tools act on an OpenEnv server: a stand-in for the real system, with its own data. Each conversation in this batch runs in its own fresh copy of that system, called an environment. An environment is started from a set of reset arguments, and some of those arguments choose what the environment starts with: which data is loaded, who the session acts as, and so on.

After you plan, Kiln picks the reset arguments for each scenario and finds what the scenario needs in that environment. You don't pick them, and you can't see the data. What follows tells you what the starting states are like, so your scenarios are plausible for this system and cover the situations it can be in.

How to use it:
- Write scenarios that could happen in at least one of the starting states below.
- Spread the batch across them, rather than writing every scenario for the richest one.
- Use it for the kinds of things that exist and the situations they can be in. Don't name specific items, IDs, people or values from it, even when it mentions them.
- If a scenario needs something none of the starting states could have, change the scenario."""
"""The planner's framing for the reset arguments that follow it. The prototype command and the
Eval Builder send the same words."""

_ARGUMENTS_PREAMBLE = (
    "Read from the server's reset schema. The server's owner wrote each description. "
    "Values are listed when the argument has a fixed set."
)


@dataclass(frozen=True)
class ResetArgument:
    """One reset argument, nested ones by dotted path (`startup.acting_user`)."""

    path: str
    description: str | None
    values: list[JsonValue] | None


def reset_arguments(schema: dict[str, JsonValue]) -> list[ResetArgument]:
    """Every argument in the reset schema, in the schema's order.

    Local `$ref`s are resolved; a ref that is not local, is missing or loops back is an
    argument with no further structure. `X | None` is read as `X`. An object with
    properties is walked into, and listed itself only when it has a description. `values`
    come from `enum`: Kiln's reset form refuses `const` and `oneOf`, so they are not read."""
    defs = schema.get("$defs")
    walker = _Walker(defs if isinstance(defs, dict) else {})
    arguments: list[ResetArgument] = []
    for name, node in _properties(schema):
        if name in OPENENV_RESET_KEYS:
            continue
        walker.walk(name, node, depth=1, refs=(), into=arguments)
    return arguments


def reset_arguments_brief(schema: dict[str, JsonValue] | None) -> str | None:
    """The planner's reset-arguments section, or None when there is no schema or it has no
    arguments, in which case the section is left out."""
    if schema is None:
        return None
    arguments = reset_arguments(schema)
    if not arguments:
        return None
    lines = [
        RESET_ARGUMENTS_FRAMING,
        "",
        "<openenv_server_reset_arguments>",
        _ARGUMENTS_PREAMBLE,
    ]
    for argument in arguments:
        lines.append(
            f"- {argument.path}: {_indent_continuation(argument.description)}"
            if argument.description
            else f"- {argument.path}"
        )
        if argument.values:
            lines.append(
                "  Values: " + " | ".join(_render_value(v) for v in argument.values)
            )
    lines.append("</openenv_server_reset_arguments>")
    return "\n".join(lines)


class _Walker:
    def __init__(self, defs: dict[str, JsonValue]) -> None:
        self._defs = defs

    def walk(
        self,
        path: str,
        node: JsonValue,
        *,
        depth: int,
        refs: tuple[str, ...],
        into: list[ResetArgument],
    ) -> None:
        resolved, description, refs = self._resolve(node, refs)
        children = _properties(resolved) if resolved is not None else []
        if not children or depth >= MAX_ARGUMENT_DEPTH:
            into.append(ResetArgument(path, description, _enum(resolved)))
            return
        if description:
            into.append(ResetArgument(path, description, None))
        for name, child in children:
            self.walk(f"{path}.{name}", child, depth=depth + 1, refs=refs, into=into)

    def _resolve(
        self, node: JsonValue, refs: tuple[str, ...]
    ) -> tuple[dict[str, JsonValue] | None, str | None, tuple[str, ...]]:
        """The node with refs followed and a nullable wrapper removed, the outermost
        description found on the way, and the refs followed so far. None when the node
        has no structure Kiln reads (an unresolvable ref, or several non-null `anyOf`
        members)."""
        description: str | None = None
        current: JsonValue = node
        while isinstance(current, dict):
            description = description or _string(current.get("description"))
            ref = current.get("$ref")
            if isinstance(ref, str):
                name = ref.removeprefix(_LOCAL_REF_PREFIX)
                if ref == name or ref in refs or name not in self._defs:
                    return None, description, refs
                refs = (*refs, ref)
                current = self._defs[name]
                continue
            variants = current.get("anyOf")
            if isinstance(variants, list):
                non_null = [v for v in variants if not _is_null_schema(v)]
                if len(non_null) != 1:
                    return None, description, refs
                current = non_null[0]
                continue
            return current, description, refs
        return None, description, refs


def _properties(node: dict[str, JsonValue]) -> list[tuple[str, JsonValue]]:
    properties = node.get("properties")
    return list(properties.items()) if isinstance(properties, dict) else []


def _enum(node: dict[str, JsonValue] | None) -> list[JsonValue] | None:
    if node is None:
        return None
    values = node.get("enum")
    return list(values) if isinstance(values, list) and values else None


def _is_null_schema(node: JsonValue) -> bool:
    return isinstance(node, dict) and node.get("type") == "null"


def _string(value: JsonValue) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _indent_continuation(text: str) -> str:
    """Indents a description's later lines under its list item, so a listing inside a
    description doesn't read as more arguments."""
    first, *rest = text.splitlines()
    return "\n".join([first, *(f"  {line}" if line else "" for line in rest)])


def _render_value(value: JsonValue) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
