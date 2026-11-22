"""The knowledge backlog, `app/mcp/knowledge_backlog.md`: its fixed format.

`backlog_problems` reads the file and returns one problem for each broken
rule. The tests on the real file assert that it has none of each rule. The
tests on a small text apply one deliberate violation each, and assert that
exactly that rule is reported.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BACKLOG = PACKAGE_ROOT.parent / "knowledge_backlog.md"

SECTIONS = ("Ranked", "Unranked")
FIELDS = ("Kind", "Where", "Depends on", "Source")
KINDS = frozenset({"gap", "technique", "playbook", "smell", "lever", "code", "guide"})
WHERE = frozenset({"knowledge", "kiln"})
NONE = "None"
MAX_TEXT_LINES = 3
# Without a width, "one to three lines" puts no limit on the text.
MAX_LINE_CHARS = 100

FIELD_RE = re.compile(r"^- ([^:]+):(.*)$")


@dataclass
class Entry:
    title: str
    section: str
    fields: list[tuple[str, str]] = field(default_factory=list)
    text: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Problem:
    rule: str
    where: str
    message: str


def parse(text: str) -> tuple[list[str], list[Entry], list[Problem]]:
    """The H2 headings in order, the entries, and the problems of the layout
    that only the parser can see: text in a section before its first entry."""
    headings: list[str] = []
    entries: list[Entry] = []
    problems: list[Problem] = []
    current: Entry | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            headings.append(line[3:].strip())
            current = None
        elif line.startswith("### "):
            if not headings:
                problems.append(
                    Problem(
                        "sections", "file", f"an entry before the first section: {line}"
                    )
                )
            section = headings[-1] if headings else ""
            current = Entry(line[4:].strip(), section)
            entries.append(current)
        elif current is not None:
            match = FIELD_RE.match(line)
            if match and not current.text:
                current.fields.append((match.group(1), match.group(2).strip()))
            elif line.strip():
                current.text.append(line)
        elif headings and line.strip():
            problems.append(
                Problem(
                    "sections", headings[-1], f"text before the first entry: {line}"
                )
            )
    return headings, entries, problems


def backlog_problems(text: str) -> list[Problem]:
    headings, entries, problems = parse(text)
    if tuple(headings) != SECTIONS:
        problems.append(
            Problem(
                "sections",
                "file",
                f"the H2 sections must be {list(SECTIONS)}; found {headings}",
            )
        )
    titles = [e.title for e in entries]
    for entry in entries:
        problems.extend(_field_problems(entry, set(titles)))
        problems.extend(_text_problems(entry))
    for title in sorted({t for t in titles if titles.count(t) > 1}):
        problems.append(Problem("unique", title, "the title is not unique"))
    return problems


def _field_problems(entry: Entry, titles: set[str]) -> list[Problem]:
    names = tuple(name for name, _ in entry.fields)
    if names != FIELDS:
        return [
            Problem(
                "fields",
                entry.title,
                f"the fields must be {list(FIELDS)}, in order; found {list(names)}",
            )
        ]
    values = dict(entry.fields)
    problems = []

    def bad(message: str, rule: str = "fields") -> None:
        problems.append(Problem(rule, entry.title, message))

    if values["Kind"] not in KINDS:
        bad(f"Kind {values['Kind']!r} is not one of {sorted(KINDS)}")
    where = values["Where"].split(", ")
    if any(w not in WHERE for w in where) or len(set(where)) != len(where):
        bad(f"Where {values['Where']!r} must be one or more of {sorted(WHERE)}")
    if not values["Source"]:
        bad(f"Source is empty; write {NONE!r} when there is none")
    depends = values["Depends on"]
    if not depends:
        bad(f"Depends on is empty; write {NONE!r} when there is none")
    elif depends != NONE:
        for title in depends.split("; "):
            if title == entry.title:
                bad("the entry depends on itself", "depends")
            elif title not in titles:
                bad(f"Depends on names {title!r}, which is not an entry", "depends")
    return problems


def _text_problems(entry: Entry) -> list[Problem]:
    count = len(entry.text)
    if not 1 <= count <= MAX_TEXT_LINES:
        return [
            Problem(
                "text",
                entry.title,
                f"{count} lines of text; an entry has 1 to {MAX_TEXT_LINES}",
            )
        ]
    return [
        Problem(
            "text",
            entry.title,
            f"a line has {len(line)} characters; the limit is {MAX_LINE_CHARS}",
        )
        for line in entry.text
        if len(line) > MAX_LINE_CHARS
    ]


# --- the real file ---------------------------------------------------------


def _real_problems(rule: str) -> list[Problem]:
    problems = backlog_problems(BACKLOG.read_text(encoding="utf-8"))
    return [p for p in problems if p.rule == rule]


def _report(problems: list[Problem]) -> str:
    return "\n".join(f"{p.where}: {p.message}" for p in problems)


def test_the_backlog_is_outside_the_package():
    """The wheel and the app bundle hold every file of the package."""
    assert BACKLOG.is_file()
    assert not BACKLOG.is_relative_to(PACKAGE_ROOT)


def test_the_using_harness_tuner_entry_is_last_in_unranked():
    _, entries, _ = parse(BACKLOG.read_text(encoding="utf-8"))
    last = entries[-1]
    assert (last.section, last.title) == ("Unranked", "using_harness_tuner")
    assert dict(last.fields)["Kind"] == "guide"


def test_the_backlog_is_not_empty():
    """The guard that stops the tests below passing on an empty file."""
    _, entries, _ = parse(BACKLOG.read_text(encoding="utf-8"))
    for section in SECTIONS:
        assert any(e.section == section for e in entries), f"no entry in {section}"


def test_the_backlog_has_the_two_sections():
    problems = _real_problems("sections")
    assert not problems, _report(problems)


def test_each_entry_has_the_four_fields_with_valid_values():
    problems = _real_problems("fields")
    assert not problems, _report(problems)


def test_each_entry_has_one_to_three_lines_of_text():
    problems = _real_problems("text")
    assert not problems, _report(problems)


def test_titles_are_unique():
    problems = _real_problems("unique")
    assert not problems, _report(problems)


def test_depends_on_names_entries_that_exist():
    problems = _real_problems("depends")
    assert not problems, _report(problems)


# --- one deliberate violation at a time -------------------------------------

VALID = """\
# Backlog

What this is.

## Ranked

### First

- Kind: gap
- Where: knowledge, kiln
- Depends on: None
- Source: [a link](https://example.com)

One line.

## Unranked

### Second, with a comma

- Kind: technique
- Where: knowledge
- Depends on: First
- Source: None

One line.
Two lines.
Three lines.

### Third

- Kind: guide
- Where: kiln
- Depends on: First; Second, with a comma
- Source: a short reference

One line.
"""


def test_a_valid_backlog_has_no_problem():
    assert backlog_problems(VALID) == []


def _swap_sections(text: str) -> str:
    head, rest = text.split("## Ranked\n", 1)
    ranked, unranked = rest.split("## Unranked\n", 1)
    return f"{head}## Unranked\n{unranked}\n## Ranked\n{ranked}"


def _add_a_second_first(text: str) -> str:
    _, first = text.split("## Ranked\n", 1)
    return text + first.split("## Unranked\n", 1)[0]


def _replace(old: str, new: str):
    def apply(text: str) -> str:
        assert old in text, old
        return text.replace(old, new, 1)

    return apply


VIOLATIONS = {
    "no-unranked": (_replace("## Unranked\n", ""), "sections"),
    "an-extra-section": (
        _replace("## Unranked\n", "## Other\n\n## Unranked\n"),
        "sections",
    ),
    "sections-out-of-order": (_swap_sections, "sections"),
    "text-before-the-first-entry": (
        _replace("## Ranked\n\n", "## Ranked\n\nA stray line.\n\n"),
        "sections",
    ),
    "an-entry-before-the-sections": (
        _replace(
            "## Ranked\n",
            "### Zeroth\n\n- Kind: gap\n- Where: kiln\n"
            "- Depends on: None\n- Source: None\n\nOne line.\n\n## Ranked\n",
        ),
        "sections",
    ),
    "a-missing-field": (_replace("- Source: None\n", ""), "fields"),
    "fields-out-of-order": (
        _replace("- Kind: guide\n- Where: kiln\n", "- Where: kiln\n- Kind: guide\n"),
        "fields",
    ),
    "an-unknown-kind": (_replace("- Kind: guide", "- Kind: chore"), "fields"),
    "a-detector-kind": (_replace("- Kind: guide", "- Kind: detector"), "fields"),
    "a-tuner-where": (
        _replace(
            "- Where: kiln\n- Depends on: First;",
            "- Where: tuner\n- Depends on: First;",
        ),
        "fields",
    ),
    "an-unknown-where": (_replace("- Where: knowledge", "- Where: docs"), "fields"),
    "where-joined-with-and": (
        _replace("- Where: knowledge, kiln", "- Where: knowledge and kiln"),
        "fields",
    ),
    "a-repeated-where": (
        _replace("- Where: knowledge, kiln", "- Where: kiln, kiln"),
        "fields",
    ),
    "an-empty-source": (_replace("- Source: None", "- Source:"), "fields"),
    "an-empty-depends-on": (_replace("- Depends on: None", "- Depends on:"), "fields"),
    "no-text": (_replace("One line.\n", ""), "text"),
    "four-lines-of-text": (
        _replace("Three lines.\n", "Three lines.\nFour lines.\n"),
        "text",
    ),
    "a-line-over-the-width": (
        _replace("Two lines.\n", "x" * (MAX_LINE_CHARS + 1) + "\n"),
        "text",
    ),
    "a-duplicate-title": (_add_a_second_first, "unique"),
    "an-unknown-dependency": (
        _replace("Depends on: First\n", "Depends on: Zeroth\n"),
        "depends",
    ),
    "a-dependency-on-itself": (
        _replace("Depends on: First; Second", "Depends on: Third; Second"),
        "depends",
    ),
}


@pytest.mark.parametrize("case", sorted(VIOLATIONS))
def test_a_violation_is_reported(case):
    change, rule = VIOLATIONS[case]
    problems = backlog_problems(change(VALID))
    assert {p.rule for p in problems} == {rule}, problems
