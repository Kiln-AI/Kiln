"""Noise rules and JSON comparison: what counts as a difference between a result the
reference system returned and the one the world returned for the same call.

Every rule is data. `ScrubRules` arrives from the driver's config file and names the
fields whose *value* is noise (`placeholder_fields`, compared as present-or-null),
the fields that are dropped outright (`ignored_fields`), the arguments compared by type
only (`free_text_fields`), the server-minted ids compared by presence (`id_fields`), and
the recorded error codes that exclude a step from replay altogether
(`transport_codes`). Nothing here knows which product is being replicated.

Two structural differences between the arms are deliberately *not* scrubbed away:

- A world runs on a frozen clock, so rows it writes in one call share a `created_at` the
  reference system's rows do not. Timestamps therefore differ in kind, not only in value,
  which is why every time field belongs in `placeholder_fields` rather than being compared.
  Their knock-on effect on *ordering* is left visible: list order is compared as recorded
  (functional spec §9.4), so a tie broken differently by the two systems surfaces as a
  divergence class on the list path, which is a finding about the world's ordering rule.
- A result's `id` is minted by whichever system answered. It is compared presence-only
  unless the recorded value is in `exact_ids` — the ids a later call in the same episode
  used as an argument, which must therefore map.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import JsonValue

FieldClass = Literal["id", "enum", "number", "free_text", "other"]
"""How a field is compared. Only `free_text` and `id` change the comparison; the rest are
compared exactly. Nothing here dispatches on it — the rules are frozensets of field names,
which is the same statement as data — so it exists for a driver or a report that wants to
name the class a field was in."""

PRESENT = "<present>"
"""What a non-null placeholder field is replaced by, so presence compares and value does not."""

MISSING = "<missing>"
"""What a key absent from one side is reported as."""

_INDEX = re.compile(r"/\d+(?=/|$)")

SCRUB_KEYS = (
    "placeholder_fields",
    "ignored_fields",
    "free_text_fields",
    "id_fields",
    "transport_codes",
)


@dataclass(frozen=True)
class Declared:
    """One entry of the world's declared-divergence evidence, as the harness reads it:
    the reported key (`id`), its kind, and the JSON pointers into a result it covers."""

    id: str
    kind: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ScrubRules:
    placeholder_fields: frozenset[str]
    ignored_fields: frozenset[str]
    free_text_fields: frozenset[str]
    id_fields: frozenset[str]
    transport_codes: frozenset[str]
    declared: Mapping[str, tuple[Declared, ...]]

    @classmethod
    def default(cls) -> "ScrubRules":
        """Empty rules: nothing is noise. The world's own rules live in the driver's config."""
        return cls(
            placeholder_fields=frozenset(),
            ignored_fields=frozenset(),
            free_text_fields=frozenset(),
            id_fields=frozenset(),
            transport_codes=frozenset(),
            declared={},
        )

    @classmethod
    def from_file(cls, path: Path) -> "ScrubRules":
        """The `scrub` section of a YAML (or JSON, which YAML parses) config file.

        Unknown keys are a ValueError rather than a silent no-op: a misspelled rule that
        quietly stops scrubbing would show up as a divergence class, not as a mistake."""
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, Mapping):
            raise ValueError(f"{path}: expected a mapping at the top level")
        if "scrub" not in loaded:
            raise ValueError(f"{path}: no 'scrub' section")
        section = loaded["scrub"]
        if section is None:
            section = {}
        if not isinstance(section, Mapping):
            raise ValueError(f"{path}: 'scrub' must be a mapping")
        unknown = sorted(set(section) - set(SCRUB_KEYS))
        if unknown:
            raise ValueError(
                f"{path}: unknown scrub keys {unknown}; known keys are {list(SCRUB_KEYS)}"
            )
        return cls(
            placeholder_fields=_string_set(section, "placeholder_fields", path),
            ignored_fields=_string_set(section, "ignored_fields", path),
            free_text_fields=_string_set(section, "free_text_fields", path),
            id_fields=_string_set(section, "id_fields", path),
            transport_codes=_string_set(section, "transport_codes", path),
            declared={},
        )

    def with_declared(
        self, declared: Mapping[str, tuple[Declared, ...]]
    ) -> "ScrubRules":
        return replace(self, declared=dict(declared))


def _string_set(section: Mapping[str, Any], key: str, path: Path) -> frozenset[str]:
    values = section.get(key) or []
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{path}: scrub.{key} must be a list of strings")
    return frozenset(str(value) for value in values)


@dataclass(frozen=True)
class Diff:
    """One leaf that differs, by JSON pointer into the result."""

    path: str
    recorded: JsonValue
    replayed: JsonValue
    signature: str | None = None
    """The divergence class this leaf belongs to, as the walk saw it: every list index
    replaced by `*`, object keys left alone even when they are numbers. None on a Diff
    built by hand or read back from a record, where `path_signature` is the fallback."""

    @property
    def divergence_signature(self) -> str:
        return (
            self.signature if self.signature is not None else path_signature(self.path)
        )


def declared_from_evidence(
    evidence: Mapping[str, JsonValue], tool_names: Sequence[str]
) -> dict[str, tuple[Declared, ...]]:
    """The world's evidence file as per-tool declared entries.

    `tools: ["*"]` expands to every name in `tool_names`. An entry with no `fields` is a
    ValueError: a divergence that names no path covers nothing, and silently covering
    everything (or nothing) would both be wrong."""
    entries = evidence.get("divergences")
    if not isinstance(entries, list):
        raise ValueError("evidence has no 'divergences' list")
    declared: dict[str, list[Declared]] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError(f"evidence entry is not an object: {raw!r}")
        entry_id = raw.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError(f"evidence entry has no id: {raw!r}")
        if "fields" not in raw:
            raise ValueError(f"evidence entry '{entry_id}' has no 'fields'")
        fields = raw["fields"]
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            raise ValueError(
                f"evidence entry '{entry_id}': 'fields' must be a list of strings"
            )
        if "tools" not in raw:
            raise ValueError(f"evidence entry '{entry_id}' has no 'tools'")
        tools = raw["tools"]
        if not isinstance(tools, list) or not tools:
            raise ValueError(
                f"evidence entry '{entry_id}': 'tools' must be a non-empty list of names "
                'or ["*"]'
            )
        names = (
            list(tool_names)
            if any(tool == "*" for tool in tools)
            else [str(tool) for tool in tools]
        )
        entry = Declared(
            id=entry_id,
            kind=str(raw.get("kind", "")),
            fields=tuple(str(f) for f in fields),
        )
        for name in names:
            declared.setdefault(name, []).append(entry)
    return {name: tuple(entries) for name, entries in declared.items()}


def path_signature(path: str) -> str:
    """A JSON pointer with its list indices replaced by `*`, so every element of a list
    reports as one divergence class.

    This reads the pointer alone, so an object key that happens to be all digits
    (`/by_year/2026/total`) collapses like an index and merges with its neighbours. A
    `Diff` produced by `compare` carries the signature the walk computed, which knows the
    difference; prefer `Diff.divergence_signature` and use this for a pointer that arrives
    without one (from a jsonl record, say)."""
    return _INDEX.sub("/*", path)


def scrub(value: JsonValue, rules: ScrubRules) -> JsonValue:
    """Drop the ignored fields and collapse the placeholder fields, at any depth.

    Order is preserved: a list stays in the order it was recorded in."""
    if isinstance(value, dict):
        scrubbed: dict[str, JsonValue] = {}
        for key, item in value.items():
            if key in rules.ignored_fields:
                continue
            if key in rules.placeholder_fields:
                scrubbed[key] = None if item is None else PRESENT
                continue
            scrubbed[key] = scrub(item, rules)
        return scrubbed
    if isinstance(value, list):
        return [scrub(item, rules) for item in value]
    return value


def compare(
    recorded: JsonValue,
    replayed: JsonValue,
    rules: ScrubRules,
    *,
    exact_ids: frozenset[str] = frozenset(),
) -> list[Diff]:
    """Every leaf that differs after scrubbing, as JSON pointers.

    A key present on one side only is a diff against `MISSING`. Lists of unequal length
    report one diff at the list path carrying the two lengths, and their common prefix is
    still compared, so a truncated page reports both the truncation and any value
    difference inside it."""
    diffs: list[Diff] = []
    _walk(
        scrub(recorded, rules),
        scrub(replayed, rules),
        "",
        "",
        None,
        rules,
        exact_ids,
        diffs,
    )
    return diffs


def _walk(
    recorded: JsonValue,
    replayed: JsonValue,
    path: str,
    signature: str,
    key: str | None,
    rules: ScrubRules,
    exact_ids: frozenset[str],
    diffs: list[Diff],
) -> None:
    if (
        key is not None
        and key in rules.id_fields
        and _is_id_leaf(recorded)
        and _is_id_leaf(replayed)
    ):
        # Only a leaf. An `id` that holds a list or an object is a structure the world has
        # to reproduce; taking the presence-only branch there would blind the comparison to
        # the whole subtree beneath it.
        _compare_id(recorded, replayed, path, signature, exact_ids, diffs)
        return
    if isinstance(recorded, dict) and isinstance(replayed, dict):
        for name in list(recorded) + [n for n in replayed if n not in recorded]:
            child = f"{path}/{_escape(name)}"
            child_signature = f"{signature}/{_escape(name)}"
            if name not in recorded:
                diffs.append(Diff(child, MISSING, replayed[name], child_signature))
            elif name not in replayed:
                diffs.append(Diff(child, recorded[name], MISSING, child_signature))
            else:
                _walk(
                    recorded[name],
                    replayed[name],
                    child,
                    child_signature,
                    name,
                    rules,
                    exact_ids,
                    diffs,
                )
        return
    if isinstance(recorded, list) and isinstance(replayed, list):
        if len(recorded) != len(replayed):
            diffs.append(Diff(path, len(recorded), len(replayed), signature))
        for index in range(min(len(recorded), len(replayed))):
            _walk(
                recorded[index],
                replayed[index],
                f"{path}/{index}",
                f"{signature}/*",
                key,
                rules,
                exact_ids,
                diffs,
            )
        return
    if recorded != replayed:
        diffs.append(Diff(path, recorded, replayed, signature))


def _is_id_leaf(value: JsonValue) -> bool:
    return value is None or isinstance(value, str)


def _compare_id(
    recorded: JsonValue,
    replayed: JsonValue,
    path: str,
    signature: str,
    exact_ids: frozenset[str],
    diffs: list[Diff],
) -> None:
    """A server-minted id: both strings or both null, unless a later call used this exact
    value, in which case it had to map and the values must be equal.

    "Both strings" is the whole check, not "both non-null": a string against a number is a
    shape difference, and the point of the presence rule is that the *value* is minted by
    whichever system answered, not that the field may be anything at all."""
    if isinstance(recorded, str) and recorded in exact_ids:
        if recorded != replayed:
            diffs.append(Diff(path, recorded, replayed, signature))
        return
    if isinstance(recorded, str) != isinstance(replayed, str):
        diffs.append(Diff(path, recorded, replayed, signature))


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def normalize_arguments(
    arguments: Mapping[str, JsonValue], rules: ScrubRules
) -> dict[str, JsonValue]:
    """Arguments as the decision comparison sees them: scrubbed, then every free-text
    field replaced by its JSON type name, so a reworded comment is agreement and a
    missing one is not."""
    scrubbed = scrub(dict(arguments), rules)
    typed = _type_free_text(scrubbed, rules)
    if not isinstance(typed, dict):  # pragma: no cover - scrub preserves the shape
        raise ValueError("normalize_arguments expects an object")
    return typed


def _type_free_text(value: JsonValue, rules: ScrubRules) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: json_type_name(item)
            if key in rules.free_text_fields
            else _type_free_text(item, rules)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_type_free_text(item, rules) for item in value]
    return value


def json_type_name(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def is_declared(
    tool_name: str, diffs: Sequence[Diff], rules: ScrubRules
) -> tuple[str, ...]:
    """The ids of the declared entries covering every diff, or () when any diff is
    uncovered. A pointer covers a diff when it equals the diff's path signature or is a
    prefix of it."""
    entries = rules.declared.get(tool_name, ())
    covering: list[str] = []
    for diff in diffs:
        signature = diff.divergence_signature
        matched = [
            entry.id
            for entry in entries
            if any(_covers(pointer, signature) for pointer in entry.fields)
        ]
        if not matched:
            return ()
        for entry_id in matched:
            if entry_id not in covering:
                covering.append(entry_id)
    return tuple(covering)


def _covers(pointer: str, signature: str) -> bool:
    return signature == pointer or signature.startswith(pointer + "/")


def as_json(value: Any) -> JsonValue:
    """A value reduced to something json.dumps can write, for the jsonl records."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value
