"""The structural rules of the knowledge trees, one deliberate violation at a
time.

`build_tree` writes a small valid skill. Each test applies one change and
asserts that the check reports exactly the rule it breaks, and nothing else.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from kiln_mcp_server.skill_checks.knowledge_check import KNOWLEDGE_RULES, check
from kiln_mcp_server.skill_checks.knowledge_index import (
    read_block,
    render_blocks,
    write_blocks,
)
from kiln_mcp_server.skill_checks.knowledge_load import load, resolve_link
from kiln_mcp_server.skill_checks.knowledge_schema import (
    INDEX_BLOCKS,
    MAX_CHARS,
    Problem,
)
from kiln_mcp_server.skill_checks.tree_check import check_tree, tree_paths

LEVERS = "references/levers"
TECHNIQUES = "references/improving_agents/techniques"
PLAYBOOKS = "references/improving_agents/playbooks"
SMELLS = "references/improving_agents/smells"
LEVERS_INDEX = "references/levers/index.md"
IMPROVING_INDEX = "references/improving_agents/index.md"
API_DOC = "references/knowledge/api_docs/post_api_prompts.md"

SKILL_MD = f"""\
---
name: kiln
description: Work with Kiln.
---

# Kiln

Levers: `{LEVERS_INDEX}`. Ideas: `{IMPROVING_INDEX}`.
"""

LEVER = f"""\
---
title: The prompt
description: The prompt text that a run config sends to the model, in a test tree.
reviewed: 2026-01-01
api_docs:
  - {API_DOC}
---

# The prompt

## What it is

The prompt.

## How to change it

A new prompt.

## Limits

None.

## See also

None.
"""

TECHNIQUE = f"""\
---
title: One technique
description: A technique of the test tree, which edits the prompt of the agent.
reviewed: 2026-01-01
status: active
levers:
  - prompt
applies_to: all
cost: low
---

# One technique

## When to use

When a test needs it.

## When not to use

Never otherwise.

## Alternatives

None.

## How

Edit the [prompt]({LEVERS}/prompt.md).

## Check that it took effect

Read a trace.

## Budget

Cheap.

## If it does not move the evals

It depends. On the test.

## Priors

- **A test agent.** One line was tried. It worked.
  Source: own experiment. 2026-01-01.

## Confidence

High, in a test.
"""

DORMANT = TECHNIQUE.replace("status: active", "status: dormant")

PLAYBOOK = f"""\
---
title: One playbook
description: A playbook of the test tree, for a failure that the traces show.
reviewed: 2026-01-01
kind: failure
applies_to:
  - tools
  - single_turn
---

# One playbook

## Situation

The trace shows a failure.

## What to try, in order

1. [One technique]({TECHNIQUES}/t-one.md), when the test says so.

## What not to do yet

Nothing else.

## Budget

The order does not change with the budget.
"""

SMELL = f"""\
---
title: One smell
description: A smell of the test tree, which a reader of the design can find.
reviewed: 2026-01-01
applies_to: all
---

# One smell

## What it is

A smell.

## How to recognise it

A sign.

## How to confirm it

A check.

## What it blocks

Nothing.

## Remedies

- [One playbook]({PLAYBOOKS}/p-one.md), when it fits.
"""


def _index(name: str, blocks: tuple[str, ...]) -> str:
    body = "".join(
        f"\n## {block}\n\n<!-- BEGIN GENERATED: {block} -->\n"
        f"<!-- END GENERATED: {block} -->\n"
        for block in blocks
    )
    return f"# {name}\n\nHand-written text.\n{body}"


@dataclass
class Tree:
    root: Path

    def write(self, key: str, text: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def read(self, key: str) -> str:
        return (self.root / key).read_bytes().decode("utf-8")

    def edit(self, key: str, old: str, new: str) -> None:
        text = self.read(key)
        assert old in text, f"{old!r} is not in {key}"
        self.write(key, text.replace(old, new, 1))

    def problems(self, *, rebuild: bool = True) -> list[Problem]:
        """The check's problems. With `rebuild`, the blocks are written first,
        so that a change is not also reported as a stale index."""
        if rebuild:
            write_blocks(load(self.root))
        return check(load(self.root), tree=tree_paths(self.root))

    def rules(self) -> set[str]:
        return {p.rule for p in self.problems()}


def build_tree(parent: Path) -> Tree:
    """A small valid skill in `parent`: the two index files, the lever
    `prompt` with one endpoint doc, the technique `t-one`, the playbook
    `p-one` and the smell `s-one`."""
    tree = Tree(parent / "skill")
    tree.write("SKILL.md", SKILL_MD)
    for index, blocks in INDEX_BLOCKS.items():
        tree.write(index, _index(index, blocks))
    tree.write(API_DOC, "# POST /api/prompts\n")
    tree.write(f"{LEVERS}/prompt.md", LEVER)
    tree.write(f"{TECHNIQUES}/t-one.md", TECHNIQUE)
    tree.write(f"{PLAYBOOKS}/p-one.md", PLAYBOOK)
    tree.write(f"{SMELLS}/s-one.md", SMELL)
    write_blocks(load(tree.root))
    return tree


@pytest.fixture
def tree(tmp_path) -> Tree:
    return build_tree(tmp_path)


def _only(tree: Tree, rule: str, *, rebuild: bool = True) -> list[Problem]:
    problems = tree.problems(rebuild=rebuild)
    assert {p.rule for p in problems} == {rule}, problems
    return problems


def test_a_valid_minimal_tree_has_no_problem(tree):
    assert tree.problems(rebuild=False) == []


def test_a_valid_minimal_tree_passes_the_tree_check(tree):
    """The index rows name each document by its full path, so the tree check
    reaches every knowledge document from `SKILL.md` through them."""
    assert check_tree(tree.root) == []


def test_a_skill_with_no_knowledge_tree_has_no_problem(tmp_path):
    root = tmp_path / "skill"
    (root / "references" / "client_guidance" / "chat").mkdir(parents=True)
    (root / "SKILL.md").write_text("# Kiln\n")
    assert check(load(root), tree=tree_paths(root)) == []


def test_each_rule_has_a_name():
    assert len(set(KNOWLEDGE_RULES)) == len(KNOWLEDGE_RULES) == 20


# ---- front-matter ----


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("reviewed: 2026-01-01\n", ""),
        ("reviewed: 2026-01-01\n", "reviewed: 2026-01-01\nowner: someone\n"),
        ("title: One playbook", "title: P"),
        ("title: One playbook", "title: " + "x" * 61),
        (
            "description: A playbook of the test tree, for",
            "description: A playbook | of the test tree, for",
        ),
        (
            "description: A playbook of the test tree, for a failure that the"
            " traces show.",
            "description: Short.",
        ),
        ("kind: failure", "kind: wish"),
        ("applies_to:\n  - tools\n  - single_turn\n", "applies_to: []\n"),
        ("title: One playbook", "title: [unclosed"),
        ("---\ntitle", "title"),
        ("\n---\n\n# One playbook", "\n\n# One playbook"),
        ("---\ntitle", "---\n- a list\n---\ntitle"),
        ("reviewed: 2026-01-01", "reviewed: 2026-02-30"),
    ],
    ids=[
        "missing-key",
        "unknown-key",
        "short-title",
        "long-title",
        "pipe-in-description",
        "short-description",
        "bad-kind",
        "empty-applies-to",
        "bad-yaml",
        "no-front-matter",
        "front-matter-not-closed",
        "front-matter-not-a-map",
        "impossible-date",
    ],
)
def test_front_matter_is_reported(tree, old, new):
    tree.edit(f"{PLAYBOOKS}/p-one.md", old, new)
    [problem] = _only(tree, "front-matter")
    assert problem.path == f"{PLAYBOOKS}/p-one.md"


@pytest.mark.parametrize(
    ("today", "rules"),
    [
        (date(2026, 3, 2), set()),
        (date(2026, 3, 1), set()),
        (date(2026, 2, 28), {"front-matter"}),
    ],
    ids=["same-day", "one-day-ahead", "two-days-ahead"],
)
def test_a_review_date_may_be_one_day_after_today(tree, monkeypatch, today, rules):
    """A document dated "today" east of UTC is one day ahead of the UTC
    date, and passes everywhere."""
    tree.edit(f"{PLAYBOOKS}/p-one.md", "reviewed: 2026-01-01", "reviewed: 2026-03-02")
    monkeypatch.setattr(
        "kiln_mcp_server.skill_checks.knowledge_schema.utc_today", lambda: today
    )
    assert tree.rules() == rules


def test_a_title_on_two_lines_is_reported(tree):
    tree.edit(f"{LEVERS}/prompt.md", "title: The prompt", 'title: "The\\nprompt"')
    _only(tree, "front-matter")


def test_load_records_a_problem_and_does_not_raise(tree):
    tree.edit(f"{SMELLS}/s-one.md", "title: One smell", "title: : : [")
    doc = load(tree.root).get("smells", "s-one")
    assert doc is not None and doc.meta is None
    assert [p.rule for p in doc.problems] == ["front-matter"]


def test_a_document_that_is_not_utf8_is_reported_and_does_not_raise(tree):
    (tree.root / LEVERS / "prompt.md").write_bytes(b"---\ntitle: \xff\n")
    problems = tree.problems()
    assert any(
        p.rule == "encoding" and p.path == f"{LEVERS}/prompt.md" for p in problems
    )
    # The lever has no readable sections, and the technique that links it
    # still does.
    assert {p.rule for p in problems} == {"encoding", "sections"}


# ---- id, sections, size, shape ----


def test_id_is_reported(tree):
    tree.write(f"{TECHNIQUES}/Bad_Id.md", TECHNIQUE)
    [problem] = _only(tree, "id")
    assert problem.path == f"{TECHNIQUES}/Bad_Id.md"


def test_a_lever_id_with_an_underscore_is_accepted(tree):
    tree.write(f"{LEVERS}/new_tool.md", LEVER.replace("The prompt", "New tools"))
    tree.edit(f"{TECHNIQUES}/t-one.md", "  - prompt\n", "  - prompt\n  - new_tool\n")
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        f"Edit the [prompt]({LEVERS}/prompt.md).",
        f"Edit the [prompt]({LEVERS}/prompt.md) and add a"
        f" [tool]({LEVERS}/new_tool.md).",
    )
    assert tree.problems() == []


@pytest.mark.parametrize("name", ["_tool", "new__tool", "new_tool_", "New_tool"])
def test_a_lever_id_with_a_bad_underscore_is_reported(tree, name):
    tree.write(f"{LEVERS}/{name}.md", LEVER)
    [problem] = _only(tree, "id")
    assert problem.path == f"{LEVERS}/{name}.md"
    assert "'-' or '_'" in problem.message


def test_an_underscore_outside_a_lever_id_is_reported(tree):
    tree.write(f"{TECHNIQUES}/t_two.md", TECHNIQUE)
    [problem] = _only(tree, "id")
    assert problem.path == f"{TECHNIQUES}/t_two.md"
    assert "'_'" not in problem.message


def test_sections_is_reported(tree):
    tree.edit(
        f"{TECHNIQUES}/t-one.md", "## When not to use\n\nNever otherwise.\n\n", ""
    )
    _only(tree, "sections")


def test_the_old_lever_heading_is_reported(tree):
    tree.edit(
        f"{LEVERS}/prompt.md", "## How to change it", "## How the tuner changes it"
    )
    _only(tree, "sections")


def test_sections_out_of_order_is_reported(tree):
    tree.edit(
        f"{SMELLS}/s-one.md",
        "## How to confirm it\n\nA check.\n\n## What it blocks\n\nNothing.\n",
        "## What it blocks\n\nNothing.\n\n## How to confirm it\n\nA check.\n",
    )
    _only(tree, "sections")


def test_an_empty_section_is_reported(tree):
    tree.edit(f"{LEVERS}/prompt.md", "## Limits\n\nNone.\n", "## Limits\n\n")
    [problem] = _only(tree, "sections")
    assert "'Limits' is empty" in problem.message


@pytest.mark.parametrize(
    "comment",
    ["<!-- fill me -->", "<!-- one -->\n<!--\ntwo\n-->"],
    ids=["one-line", "several"],
)
def test_a_section_that_holds_only_a_comment_is_reported(tree, comment):
    tree.edit(
        f"{LEVERS}/prompt.md", "## Limits\n\nNone.\n", f"## Limits\n\n{comment}\n"
    )
    [problem] = _only(tree, "sections")
    assert "'Limits' is empty" in problem.message


def test_a_section_with_a_comment_and_text_is_accepted(tree):
    tree.edit(f"{LEVERS}/prompt.md", "None.\n", "<!-- a note -->\nNone.\n")
    assert tree.problems() == []


def test_other_sections_can_follow_the_required_ones(tree):
    tree.write(f"{LEVERS}/prompt.md", LEVER + "\n## Notes\n\nMore.\n")
    assert tree.problems() == []


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        (f"{LEVERS}/prompt.md", "## Limits\n\nNone.", "## Limits\n\n{{TEXT}}"),
        (f"{LEVERS}/prompt.md", "title: The prompt", 'title: "{{TITLE}}"'),
        (f"{LEVERS}/prompt.md", "# The prompt\n", "# {{TITLE}}\n"),
        (IMPROVING_INDEX, "Hand-written text.", "Hand-written {{TEXT}}."),
        (
            f"{TECHNIQUES}/t-one.md",
            "Read a trace.",
            f"Read [{{{{X}}}}]({TECHNIQUES}/t-one/recipe.md).",
        ),
    ],
    ids=["section", "title", "heading", "index-file", "in-a-link"],
)
def test_placeholder_is_reported(tree, path, old, new):
    if path.startswith(TECHNIQUES):
        tree.write(f"{TECHNIQUES}/t-one/recipe.md", "# Recipe\n\nMore detail.\n")
    tree.edit(path, old, new)
    [problem] = _only(tree, "placeholder")
    assert problem.path == path
    assert "{{" in problem.message


def test_a_placeholder_in_a_sub_file_is_reported(tree):
    tree.write(f"{TECHNIQUES}/t-one/recipe.md", "# Recipe\n\n{{TEXT}}\n")
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        "Read a trace.",
        f"See [the recipe]({TECHNIQUES}/t-one/recipe.md).",
    )
    [problem] = _only(tree, "placeholder")
    assert problem.path == f"{TECHNIQUES}/t-one/recipe.md"
    assert problem.message.startswith("line 3 ")


def test_a_placeholder_inside_a_fence_is_accepted(tree):
    tree.edit(
        f"{LEVERS}/prompt.md",
        "## See also\n\nNone.",
        "## See also\n\nNone.\n\n```\ntitle: {{TITLE}}\n```",
    )
    assert tree.problems() == []


def test_size_is_reported(tree):
    tree.write(
        f"{SMELLS}/s-one.md", SMELL + "\n## Notes\n\n" + "x" * MAX_CHARS["smells"]
    )
    _only(tree, "size")


def test_shape_is_reported(tree):
    tree.edit(f"{PLAYBOOKS}/p-one.md", "  - single_turn", "  - quantum")
    [problem] = _only(tree, "shape")
    assert "'quantum'" in problem.message


# ---- links ----


def test_link_is_reported(tree):
    tree.edit(
        f"{LEVERS}/prompt.md",
        "## See also\n\nNone.",
        "## See also\n\n[x](references/levers/gone.md)",
    )
    _only(tree, "link")


@pytest.mark.parametrize(
    "target",
    ["../levers/prompt.md", "prompt.md", "./references/levers/prompt.md"],
    ids=["file-relative", "bare-name", "dot-segment"],
)
def test_a_link_not_written_from_the_skill_root_is_reported(tree, target):
    tree.edit(
        f"{LEVERS}/prompt.md", "## See also\n\nNone.", f"## See also\n\n[x]({target})"
    )
    [problem] = _only(tree, "link")
    assert "full path from the skill root" in problem.message


def test_a_link_spelled_in_another_case_is_reported(tree):
    tree.edit(f"{TECHNIQUES}/t-one.md", f"{LEVERS}/prompt.md", f"{LEVERS}/Prompt.md")
    # The How section then links no lever document either.
    assert tree.rules() == {"link", "technique-lever-links"}


def test_a_link_to_a_skill_file_outside_the_knowledge_trees_is_accepted(tree):
    tree.edit(
        f"{LEVERS}/prompt.md",
        "## See also\n\nNone.",
        f"## See also\n\n[doc]({API_DOC})",
    )
    assert tree.problems() == []


def test_an_external_link_and_an_anchor_are_not_reported(tree):
    tree.edit(
        f"{LEVERS}/prompt.md",
        "## See also\n\nNone.",
        "## See also\n\n[a](https://example.com/a) [b](#limits)"
        f" [c]({LEVERS}/prompt.md#limits)",
    )
    assert tree.problems() == []


@pytest.mark.parametrize(
    "fence",
    [
        "```\n[x](gone.md)\n```python\n[y](gone.md)\n```",
        "````\n[x](gone.md)\n```\n[y](gone.md)\n````",
        "~~~\n[x](gone.md)\n```\n~~~",
    ],
    ids=["info-string-does-not-close", "shorter-fence-does-not-close", "tilde"],
)
def test_a_fence_closes_only_on_a_matching_fence(tree, fence):
    tree.edit(f"{LEVERS}/prompt.md", "## See also\n\nNone.", f"## See also\n\n{fence}")
    assert tree.problems() == []
    tree.edit(f"{LEVERS}/prompt.md", fence, fence + "\n\n[z](gone.md)")
    [problem] = _only(tree, "link")
    assert "gone.md" in problem.message


def test_a_link_inside_a_fence_is_not_a_link(tree):
    tree.edit(
        f"{LEVERS}/prompt.md",
        "## See also\n\nNone.",
        "## See also\n\n```\n[x](gone.md)\n```",
    )
    assert tree.problems() == []
    lever = load(tree.root).get("levers", "prompt")
    assert lever is not None and lever.links == ()


@pytest.mark.parametrize(
    ("target", "resolved"),
    [
        (f"{LEVERS}/prompt.md", f"{LEVERS}/prompt.md"),
        (f"{LEVERS}/Prompt.md", None),
        (f"{LEVERS}/../levers/prompt.md", None),
        ("references/./levers/prompt.md", None),
        ("references/levers", None),
    ],
)
def test_resolve_link_is_an_exact_lookup(target, resolved):
    assert resolve_link(target, frozenset({f"{LEVERS}/prompt.md"})) == resolved


def test_a_dormant_technique_may_have_no_inbound_link(tree):
    tree.write(f"{TECHNIQUES}/t-asleep.md", DORMANT)
    assert tree.problems() == []


def test_a_playbook_that_loses_its_dormant_step_is_reported(tree):
    tree.edit(f"{TECHNIQUES}/t-one.md", "status: active", "status: dormant")
    tree.edit(
        f"{PLAYBOOKS}/p-one.md",
        f"1. [One technique]({TECHNIQUES}/t-one.md), when the test says so.",
        "Nothing yet.",
    )
    [problem] = _only(tree, "playbook-steps")
    assert problem.path == f"{PLAYBOOKS}/p-one.md"


# ---- levers and techniques ----


def test_technique_lever_ids_is_reported(tree):
    tree.edit(f"{TECHNIQUES}/t-one.md", "  - prompt\n", "  - prompt\n  - ghost\n")
    [problem] = _only(tree, "technique-lever-ids")
    assert "'ghost'" in problem.message


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("api_docs/post_api_prompts.md", "is not under"),
        ("references/knowledge/api_docs/post_api_gone.md", "is not a file"),
        ("references/knowledge/api_docs/prompts_api_list.md", "is a catalogue"),
        ("references/knowledge/api_docs/api_index.md", "is a catalogue"),
    ],
    ids=["outside-the-reference", "missing", "catalogue", "catalogue-index"],
)
def test_lever_api_docs_is_reported(tree, value, message):
    tree.write("references/knowledge/api_docs/prompts_api_list.md", "# Prompts API\n")
    tree.write("references/knowledge/api_docs/api_index.md", "# API\n")
    tree.edit(f"{LEVERS}/prompt.md", f"  - {API_DOC}", f"  - {value}")
    [problem] = _only(tree, "lever-api-docs")
    assert message in problem.message


def test_a_lever_with_no_api_docs_is_accepted(tree):
    tree.edit(f"{LEVERS}/prompt.md", f"api_docs:\n  - {API_DOC}\n", "")
    assert tree.problems() == []
    block = read_block(tree.read(LEVERS_INDEX), "levers")
    assert block is not None and "| none |" in block


def test_technique_lever_links_is_reported(tree):
    tree.edit(
        f"{TECHNIQUES}/t-one.md", f"Edit the [prompt]({LEVERS}/prompt.md).", "Edit it."
    )
    [problem] = _only(tree, "technique-lever-links")
    assert "does not link" in problem.message


def test_a_lever_linked_and_not_named_is_reported(tree):
    tree.write(
        f"{LEVERS}/skill.md",
        LEVER.replace("The prompt", "Skills").replace("prompt text", "skill text"),
    )
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        f"({LEVERS}/prompt.md).",
        f"({LEVERS}/prompt.md) and a [skill]({LEVERS}/skill.md).",
    )
    [problem] = _only(tree, "technique-lever-links")
    assert "'skill'" in problem.message


def test_technique_stance_is_reported(tree):
    tree.edit(f"{TECHNIQUES}/t-one.md", "It depends. On the test.", "Perhaps keep it.")
    _only(tree, "technique-stance")


@pytest.mark.parametrize("stance", ["Keep it.", "It must move an eval."])
def test_each_stance_is_accepted(tree, stance):
    tree.edit(f"{TECHNIQUES}/t-one.md", "It depends.", stance)
    assert tree.problems() == []


def test_technique_priors_is_reported(tree):
    tree.edit(f"{TECHNIQUES}/t-one.md", "Source: own experiment.", "Source: a friend.")
    _only(tree, "technique-priors")


def test_priors_that_are_not_a_list_are_reported(tree):
    tree.edit(f"{TECHNIQUES}/t-one.md", "## Priors\n\n", "## Priors\n\nSome text.\n\n")
    _only(tree, "technique-priors")


def test_no_prior_is_accepted(tree):
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        "- **A test agent.** One line was tried. It worked.\n"
        "  Source: own experiment. 2026-01-01.",
        "None yet.",
    )
    assert tree.problems() == []


PLAYBOOK_PRIOR = (
    "\n## Priors\n\n- **A test agent.** One step was tried. It worked.\n"
    "  Source: public. 2026-01-01.\n"
)


def test_a_playbook_prior_is_accepted(tree):
    tree.edit(
        f"{PLAYBOOKS}/p-one.md",
        "with the budget.\n",
        "with the budget.\n" + PLAYBOOK_PRIOR,
    )
    assert tree.problems() == []


def test_playbook_priors_is_reported(tree):
    bad = PLAYBOOK_PRIOR.replace("Source: public.", "Source: a friend.")
    tree.edit(f"{PLAYBOOKS}/p-one.md", "with the budget.\n", "with the budget.\n" + bad)
    _only(tree, "playbook-priors")


def test_alternatives_is_reported(tree):
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        "## Alternatives\n\nNone.",
        f"## Alternatives\n\n[a playbook]({PLAYBOOKS}/p-one.md), when it fits.",
    )
    _only(tree, "alternatives")


# ---- playbooks and smells ----


def test_playbook_steps_is_reported(tree):
    tree.edit(f"{PLAYBOOKS}/p-one.md", f"{TECHNIQUES}/t-one.md", f"{SMELLS}/s-one.md")
    # The step links a smell (not allowed), and so no technique (required).
    problems = _only(tree, "playbook-steps")
    assert len(problems) == 2


def test_a_playbook_with_no_step_link_is_reported(tree):
    tree.edit(
        f"{PLAYBOOKS}/p-one.md",
        f"1. [One technique]({TECHNIQUES}/t-one.md), when the test says so.",
        "1. Try something.",
    )
    _only(tree, "playbook-steps")


@pytest.mark.parametrize("self_link", ["#budget", f"{PLAYBOOKS}/p-one.md#budget"])
def test_a_self_link_is_not_a_playbook_step(tree, self_link):
    tree.edit(
        f"{PLAYBOOKS}/p-one.md",
        "\n## What not to do yet",
        f"\n2. [Budget]({self_link}), when the budget is small.\n\n## What not to do yet",
    )
    assert tree.problems() == []
    tree.edit(
        f"{PLAYBOOKS}/p-one.md",
        f"1. [One technique]({TECHNIQUES}/t-one.md), when the test says so.\n",
        "",
    )
    problems = tree.problems()
    assert any(
        p.rule == "playbook-steps" and "at least one" in p.message for p in problems
    ), problems


@pytest.mark.parametrize("self_link", ["#remedies", f"{SMELLS}/s-one.md#remedies"])
def test_a_self_link_in_remedies_is_not_reported(tree, self_link):
    tree.edit(
        f"{SMELLS}/s-one.md",
        f"- [One playbook]({PLAYBOOKS}/p-one.md), when it fits.",
        f"- [One playbook]({PLAYBOOKS}/p-one.md), when it fits.\n"
        f"- [The list above]({self_link}), when the first one fails.",
    )
    assert tree.problems() == []


def test_smell_remedies_is_reported(tree):
    tree.edit(f"{SMELLS}/s-one.md", f"{PLAYBOOKS}/p-one.md", f"{LEVERS}/prompt.md")
    _only(tree, "smell-remedies")


def test_a_smell_with_no_remedy_is_reported(tree):
    tree.edit(
        f"{SMELLS}/s-one.md",
        f"- [One playbook]({PLAYBOOKS}/p-one.md), when it fits.",
        "- Fix it.",
    )
    [problem] = _only(tree, "smell-remedies")
    assert "at least one" in problem.message


@pytest.mark.parametrize("key", ["detected_by", "detectors"])
def test_a_smell_detector_key_is_bad_front_matter(tree, key):
    tree.edit(
        f"{SMELLS}/s-one.md", "applies_to: all\n", f"applies_to: all\n{key}: []\n"
    )
    _only(tree, "front-matter")


# ---- sub-files, index, strays ----


def test_a_linked_sub_file_is_accepted(tree):
    tree.write(f"{TECHNIQUES}/t-one/recipe.md", "# Recipe\n\nMore detail.\n")
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        "Read a trace.",
        f"Read a trace. See [the recipe]({TECHNIQUES}/t-one/recipe.md).",
    )
    assert tree.problems() == []
    doc = load(tree.root).get("subfile", "recipe")
    assert doc is not None and doc.meta is None


def test_subfile_is_reported(tree):
    tree.write(f"{TECHNIQUES}/t-one/recipe.md", "# Recipe\n")
    [problem] = _only(tree, "subfile")
    assert "does not link" in problem.message


def test_a_sub_file_that_is_not_markdown_is_reported(tree):
    tree.write(f"{TECHNIQUES}/t-one/data.txt", "data")
    _only(tree, "subfile")


def test_a_sub_file_with_no_owner_is_reported(tree):
    tree.write(f"{TECHNIQUES}/ghost/recipe.md", "# Recipe\n")
    [problem] = _only(tree, "subfile")
    assert "no component" in problem.message


def test_size_of_a_sub_file_is_reported(tree):
    tree.write(f"{TECHNIQUES}/t-one/recipe.md", "x" * (MAX_CHARS["subfile"] + 1))
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        "Read a trace.",
        f"See [the recipe]({TECHNIQUES}/t-one/recipe.md).",
    )
    _only(tree, "size")


def test_index_is_reported(tree):
    tree.edit(
        f"{TECHNIQUES}/t-one.md", "which edits the prompt", "which changes the prompt"
    )
    [problem] = _only(tree, "index", rebuild=False)
    assert problem.path == IMPROVING_INDEX
    assert "skill_checks build" in problem.message


def test_a_missing_block_is_reported(tree):
    tree.edit(IMPROVING_INDEX, "<!-- END GENERATED: playbooks-failure -->", "")
    [problem] = _only(tree, "index")
    assert problem.path == IMPROVING_INDEX


def test_a_missing_index_file_is_reported(tree):
    (tree.root / LEVERS_INDEX).unlink()
    [problem] = _only(tree, "index")
    assert problem.path == LEVERS_INDEX
    assert "missing" in problem.message


@pytest.mark.parametrize(
    "path",
    [
        "references/notes.md",
        "references/improving_agents/notes.md",
        "references/improving_agents/other/x.md",
        f"{LEVERS}/data.txt",
    ],
)
def test_stray_is_reported(tree, path):
    tree.write(path, "x")
    [problem] = _only(tree, "stray")
    assert problem.path == path


def test_a_file_outside_the_knowledge_trees_is_not_a_stray(tree):
    tree.write("references/knowledge/rag.md", "x")
    tree.write("references/client_guidance/chat/a/b.txt", "x")
    assert tree.problems() == []


def test_a_hidden_file_and_pycache_are_ignored(tree):
    tree.write(f"{LEVERS}/.DS_Store", "x")
    tree.write(f"{LEVERS}/__pycache__/x.pyc", "x")
    assert tree.problems() == []


# ---- the parser ----


def test_a_heading_inside_a_fence_is_not_a_section(tree):
    tree.edit(
        f"{TECHNIQUES}/t-one.md",
        f"Edit the [prompt]({LEVERS}/prompt.md).",
        f"Edit the [prompt]({LEVERS}/prompt.md).\n\n```\n## Budget\n```",
    )
    assert tree.problems() == []
    doc = load(tree.root).get("techniques", "t-one")
    assert doc is not None
    assert [s.heading for s in doc.sections].count("Budget") == 1
    how = doc.section("How")
    assert how is not None and "## Budget" in how.text


def test_document_kinds(tree):
    tree.write(f"{TECHNIQUES}/t-one/recipe.md", "# Recipe\n")
    kinds = {d.path: d.kind for d in load(tree.root).documents}
    assert kinds == {
        LEVERS_INDEX: "index",
        IMPROVING_INDEX: "index",
        f"{LEVERS}/prompt.md": "levers",
        f"{TECHNIQUES}/t-one.md": "techniques",
        f"{TECHNIQUES}/t-one/recipe.md": "subfile",
        f"{PLAYBOOKS}/p-one.md": "playbooks",
        f"{SMELLS}/s-one.md": "smells",
    }


# ---- the generated blocks ----


def test_a_dormant_technique_has_its_own_block(tree):
    tree.write(f"{TECHNIQUES}/t-asleep.md", DORMANT)
    blocks = render_blocks(load(tree.root))
    active = blocks[(IMPROVING_INDEX, "techniques")]
    dormant = blocks[(IMPROVING_INDEX, "techniques-dormant")]
    assert "t-asleep" not in active and "t-one" in active
    assert dormant == (
        "\n| Technique | Description |\n|---|---|\n"
        f"| `{TECHNIQUES}/t-asleep.md` | A technique of the test tree, which edits"
        " the prompt of the agent. |\n"
    )


def test_render_blocks_is_stable(tree):
    first = render_blocks(load(tree.root))
    assert first == render_blocks(load(tree.root))
    assert first[(IMPROVING_INDEX, "playbooks-failure")] == (
        "\n| Playbook | Applies to | Description |\n|---|---|---|\n"
        f"| `{PLAYBOOKS}/p-one.md` | tools, single_turn | A playbook of the"
        " test tree, for a failure that the traces show. |\n"
    )
    assert first[(IMPROVING_INDEX, "playbooks-goal")] == "\nNone yet.\n"
    assert first[(IMPROVING_INDEX, "techniques")] == (
        "\n| Technique | Levers | Applies to | Cost | Description |\n"
        "|---|---|---|---|---|\n"
        f"| `{TECHNIQUES}/t-one.md` | prompt | all | low | A technique of the test"
        " tree, which edits the prompt of the agent. |\n"
    )
    assert first[(IMPROVING_INDEX, "smells")] == (
        "\n| Smell | Applies to | Description |\n|---|---|---|\n"
        f"| `{SMELLS}/s-one.md` | all | A smell of the test tree, which a reader of"
        " the design can find. |\n"
    )
    assert first[(LEVERS_INDEX, "levers")] == (
        "\n| Lever | API docs | Description |\n|---|---|---|\n"
        f"| `{LEVERS}/prompt.md` | `{API_DOC}` | The prompt text that a run config"
        " sends to the model, in a test tree. |\n"
    )


def test_rows_are_sorted_by_id(tree):
    tree.write(f"{TECHNIQUES}/a-first.md", TECHNIQUE)
    block = render_blocks(load(tree.root))[(IMPROVING_INDEX, "techniques")]
    assert block.index("a-first") < block.index("t-one")


def test_build_rewrites_only_between_the_markers(tree):
    before = tree.read(IMPROVING_INDEX)
    tree.write(f"{TECHNIQUES}/t-two.md", TECHNIQUE.replace("One technique", "Two"))
    changed = write_blocks(load(tree.root))
    after = tree.read(IMPROVING_INDEX)
    assert changed == [tree.root / IMPROVING_INDEX]
    before_block = read_block(before, "techniques")
    after_block = read_block(after, "techniques")
    assert before_block is not None and after_block is not None
    assert after.replace(after_block, "") == before.replace(before_block, "")
    assert "t-two" in after_block


def test_build_leaves_a_missing_index_file_missing(tree):
    (tree.root / LEVERS_INDEX).unlink()
    assert write_blocks(load(tree.root)) == []
    assert not (tree.root / LEVERS_INDEX).exists()
