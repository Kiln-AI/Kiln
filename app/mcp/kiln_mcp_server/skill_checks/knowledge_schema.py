"""The fixed rules of the knowledge trees (`references/levers/` and
`references/improving_agents/`): their layout, their limits and the front
matter of each component type.

A component is one Markdown file. Its folder gives its type, and its file name
without `.md` gives its id. Every path here is a POSIX path from the skill
root.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

COMPONENT_ROOTS: dict[str, str] = {
    "levers": "references/levers",
    "techniques": "references/improving_agents/techniques",
    "playbooks": "references/improving_agents/playbooks",
    "smells": "references/improving_agents/smells",
}

# Index file -> the generated blocks it holds, in the order they appear.
INDEX_BLOCKS: dict[str, tuple[str, ...]] = {
    "references/levers/index.md": ("levers",),
    "references/improving_agents/index.md": (
        "smells",
        "playbooks-goal",
        "playbooks-order",
        "playbooks-failure",
        "playbooks-eval",
        "playbooks-design",
        "techniques",
        "techniques-dormant",
    ),
}

# Rewrites every generated index of the skill, then checks the tree.
BUILD_COMMAND = "uv run python -m kiln_mcp_server.skill_checks build"

API_DOCS_PREFIX = "references/knowledge/api_docs/"
API_CATALOGUE_SUFFIX = "_api_list.md"

TASK_SHAPES: tuple[str, ...] = (
    "single_turn",
    "multi_turn",
    "structured_output",
    "free_text",
    "classifier",
    "tools",
    "no_tools",
)

# Characters, not tokens: a check that needs no tokenizer gives the same
# answer on every machine. A sub-file of any component has one limit.
MAX_CHARS: dict[str, int] = {
    "levers": 6000,
    "techniques": 12000,
    "playbooks": 8000,
    "smells": 4000,
    "subfile": 20000,
}

REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "levers": ("What it is", "How to change it", "Limits", "See also"),
    "techniques": (
        "When to use",
        "When not to use",
        "Alternatives",
        "How",
        "Check that it took effect",
        "Budget",
        "If it does not move the evals",
        "Priors",
        "Confidence",
    ),
    "playbooks": (
        "Situation",
        "What to try, in order",
        "What not to do yet",
        "Budget",
    ),
    "smells": (
        "What it is",
        "How to recognise it",
        "How to confirm it",
        "What it blocks",
        "Remedies",
    ),
}

EVAL_STANCES: tuple[str, ...] = ("Keep it.", "It must move an eval.", "It depends.")
PRIOR_SOURCES: tuple[str, ...] = ("public", "own experiment", "anonymised")
NO_PRIORS = "None yet."

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Two lever ids join their words with `_` (`tool_config`, `new_tool`): they are
# the short names of the levers that experiments are recorded under.
LEVER_ID_PATTERN = re.compile(r"^[a-z0-9]+([-_][a-z0-9]+)*$")
MAX_ID_CHARS = 60

PlaybookKind = Literal["goal", "order", "failure", "eval", "design"]
PLAYBOOK_KINDS: tuple[str, ...] = get_args(PlaybookKind)

# A `reviewed:` date may be this far after the UTC date, so that a document
# dated "today" in any time zone passes on every machine.
REVIEWED_TOLERANCE = timedelta(days=1)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def default_root() -> Path:
    """The skill folder of this package on disk."""
    return Path(__file__).resolve().parents[1] / "skill"


@dataclass(frozen=True)
class Problem:
    """One broken rule; `path` is from the skill root."""

    rule: str
    path: str
    message: str


AppliesTo = Literal["all"] | list[str]


class CommonMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    reviewed: date

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _one_line(value, "title", 3, 60)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        # The description is the text of an index row: a `|` would end the
        # table cell.
        if "|" in value:
            raise ValueError("description must not hold a '|'")
        return _one_line(value, "description", 40, 200)

    @field_validator("reviewed")
    @classmethod
    def _reviewed(cls, value: date) -> date:
        if value > utc_today() + REVIEWED_TOLERANCE:
            raise ValueError(f"reviewed {value} is in the future")
        return value

    @field_validator("applies_to", check_fields=False)
    @classmethod
    def _applies_to(cls, value: AppliesTo) -> AppliesTo:
        # Each value is checked against TASK_SHAPES by the rule `shape`, so
        # that an unknown shape is reported as such and not as bad front
        # matter.
        if isinstance(value, list) and not value:
            raise ValueError("applies_to must be 'all' or a non-empty list")
        return value


class LeverMeta(CommonMeta):
    api_docs: list[str] = []


class TechniqueMeta(CommonMeta):
    status: Literal["active", "dormant"]
    levers: list[str] = Field(min_length=1)
    applies_to: AppliesTo
    cost: Literal["low", "medium", "high"]


class PlaybookMeta(CommonMeta):
    kind: PlaybookKind
    applies_to: AppliesTo


class SmellMeta(CommonMeta):
    applies_to: AppliesTo


META_MODELS: dict[str, type[CommonMeta]] = {
    "levers": LeverMeta,
    "techniques": TechniqueMeta,
    "playbooks": PlaybookMeta,
    "smells": SmellMeta,
}


def _one_line(value: str, field: str, low: int, high: int) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field} must be one line")
    if not low <= len(value) <= high:
        raise ValueError(
            f"{field} has {len(value)} characters; the limit is {low} to {high}"
        )
    return value
