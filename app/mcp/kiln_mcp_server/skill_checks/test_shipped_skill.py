"""Checks of the skill tree as shipped in this package, and of the
`knowledge-maintenance` skill that changes its knowledge."""

import re
from pathlib import Path

import pytest

from kiln_mcp_server.api_tool.tool import DEFAULT_BODY_LIMIT
from kiln_mcp_server.skill_checks.__main__ import run_check
from kiln_mcp_server.skill_checks.docs_index import DOCS_INDEX_RULE
from kiln_mcp_server.skill_checks.knowledge_check import KNOWLEDGE_RULES, check
from kiln_mcp_server.skill_checks.knowledge_load import load
from kiln_mcp_server.skill_checks.knowledge_schema import (
    BUILD_COMMAND,
    COMPONENT_ROOTS,
    META_MODELS,
    REQUIRED_SECTIONS,
    default_root,
)
from kiln_mcp_server.skill_checks.test_knowledge_check import API_DOC, build_tree
from kiln_mcp_server.skill_checks.tree_check import (
    TREE_RULES,
    check_tree,
    tree_paths,
)
from kiln_mcp_server.skill_files import (
    API_CATALOGUE_INDEX_PATH,
    HINT,
    get_index,
    read_file,
)
from kiln_mcp_server.texts import PATH_DESCRIPTION, SKILL_TOOL_DESCRIPTION

REPO_ROOT = Path(__file__).resolve().parents[4]
MAINTENANCE = REPO_ROOT / ".agents" / "skills" / "knowledge-maintenance"
MAINTENANCE_SKILL = MAINTENANCE / "SKILL.md"
MAX_MAINTENANCE_LINES = 500

# Rules whose problems do not fail the shipped-tree tests yet, each with the
# content batch that makes it pass (skill_and_content section 9).
PENDING_RULES: set[str] = {
    "tree-banned-term",  # batches 2, 4 and 5
    "tree-app-link",  # batch 3
    "tree-unreachable",  # batch 4: SKILL.md names the catalogue index
    "tree-front-matter",  # batch 6: online_url on the help articles
    "docs-index",  # batch 6
    "tree-test-split",  # batch 13a
}

# Files allowed over the size limit, each with its reason.
OVER_BODY_LIMIT_ALLOWED: dict[str, str] = {}


@pytest.fixture(scope="module")
def shipped_problems():
    return check_tree(default_root())


def test_pending_rules_are_known_rules():
    assert PENDING_RULES <= {*TREE_RULES, *KNOWLEDGE_RULES, DOCS_INDEX_RULE}


def test_the_shipped_tree_passes_every_check(shipped_problems):
    failing = [p for p in shipped_problems if p.rule not in PENDING_RULES]
    assert failing == []


def test_the_shipped_knowledge_passes_every_check():
    root = default_root()
    problems = check(load(root), tree=tree_paths(root))
    failing = [p for p in problems if p.rule not in PENDING_RULES]
    assert failing == []


def test_the_full_check_passes():
    failing = [p for p in run_check(default_root()) if p.rule not in PENDING_RULES]
    assert failing == []


def test_the_check_reads_the_served_files():
    assert tree_paths(default_root()) == frozenset(get_index().files)


def test_the_catalogue_index_exists():
    assert (default_root() / API_CATALOGUE_INDEX_PATH).is_file()
    assert API_CATALOGUE_INDEX_PATH in get_index().files


@pytest.mark.parametrize(
    "text",
    [SKILL_TOOL_DESCRIPTION, PATH_DESCRIPTION, HINT],
    ids=["tool", "path", "hint"],
)
def test_example_paths_exist(text):
    examples = re.findall(r"references/[A-Za-z0-9_./-]+\.md", text)
    assert examples
    assert [path for path in examples if path not in get_index().files] == []


def test_no_file_over_body_limit():
    index = get_index()
    sizes = {key: len(read_file(key, index)) for key in index.files}
    over = {
        key: size
        for key, size in sizes.items()
        if size > DEFAULT_BODY_LIMIT and key not in OVER_BODY_LIMIT_ALLOWED
    }
    assert over == {}


# --- the maintenance skill ---------------------------------------------------

TEMPLATES = {
    "levers": "lever.md",
    "techniques": "technique.md",
    "playbooks": "playbook.md",
    "smells": "smell.md",
}

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
COMMENT_RE = re.compile(r"[ \t]*<!--.*?-->[ \t]*\n?", re.DOTALL)

# What an author writes in place of each placeholder. The ids and the
# endpoint doc name documents of the tree that `build_tree` writes.
FILLED = {
    "TITLE": "A filled template",
    "DESCRIPTION": "A document made from its template, with each placeholder filled.",
    "REVIEWED": "2026-01-01",
    "TEXT": "Text.",
    "API_DOC": API_DOC,
    "COST": "low",
    "KIND": "failure",
    "STANCE": "It depends.",
    "LEVER_ID": "prompt",
    "LEVER_TITLE": "prompt",
    "TECHNIQUE_ID": "t-one",
    "TECHNIQUE_TITLE": "One technique",
    "PLAYBOOK_ID": "p-one",
    "PLAYBOOK_TITLE": "One playbook",
}


def _template(kind: str) -> str:
    return (MAINTENANCE / "templates" / TEMPLATES[kind]).read_text(encoding="utf-8")


def _fill(template: str) -> str:
    """The template as an author leaves it: each placeholder filled and each
    HTML comment of guidance removed."""
    unknown = set(PLACEHOLDER_RE.findall(template)) - FILLED.keys()
    assert not unknown, f"placeholders with no fixed value: {sorted(unknown)}"
    filled = PLACEHOLDER_RE.sub(lambda m: FILLED[m.group(1)], template)
    return COMMENT_RE.sub("", filled)


def test_there_is_a_template_for_each_component_type():
    assert set(TEMPLATES) == set(COMPONENT_ROOTS)
    for name in TEMPLATES.values():
        assert (MAINTENANCE / "templates" / name).is_file(), name


@pytest.mark.parametrize("kind", sorted(COMPONENT_ROOTS))
def test_each_template_gives_a_valid_document(tmp_path, kind):
    """A template cannot go out of step with the schema: filled, it passes
    every check in a valid tree."""
    tree = build_tree(tmp_path)
    tree.write(f"{COMPONENT_ROOTS[kind]}/filled-template.md", _fill(_template(kind)))
    assert tree.problems() == []
    assert load(tree.root).get(kind, "filled-template") is not None
    assert check_tree(tree.root) == []


@pytest.mark.parametrize("kind", sorted(COMPONENT_ROOTS))
def test_each_template_has_the_required_headings_and_front_matter_keys(kind):
    """The order of the template is the order of the schema, so an author who
    fills it in place gets each part where the check looks for it."""
    text = _template(kind)
    headings = tuple(re.findall(r"^## (.+)$", text, re.MULTILINE))
    assert headings == REQUIRED_SECTIONS[kind]
    front = text.split("---\n")[1]
    keys = re.findall(r"^([a-z_]+):", front, re.MULTILINE)
    assert keys == list(META_MODELS[kind].model_fields)


def test_the_maintenance_skill_is_inside_its_line_limit():
    lines = MAINTENANCE_SKILL.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_MAINTENANCE_LINES, len(lines)


def test_the_maintenance_skill_names_its_folder():
    text = MAINTENANCE_SKILL.read_text(encoding="utf-8")
    assert re.search(rf"^name: {MAINTENANCE.name}$", text, re.MULTILINE)
    assert re.search(r"^description: .{40,}$", text, re.MULTILINE)


def test_the_maintenance_skill_names_the_commands():
    text = MAINTENANCE_SKILL.read_text(encoding="utf-8")
    for command in (
        BUILD_COMMAND,
        "uv run python -m kiln_mcp_server.skill_checks check",
        "uv run python -m pytest app/mcp\n",
        "uv run ruff check",
        "uv run ruff format --check",
        "app/mcp/knowledge_backlog.md",
        "uv run python -m pytest"
        " app/mcp/kiln_mcp_server/skill_checks/test_knowledge_backlog.py",
    ):
        assert command in text, command


def test_the_maintenance_skill_links_resolve():
    # A link in a code span is an example of a link in the skill tree.
    text = re.sub(r"`[^`\n]+`", "", MAINTENANCE_SKILL.read_text(encoding="utf-8"))
    targets = re.findall(r"\]\(([^)\s#]+)\)", text)
    assert targets
    missing = [t for t in targets if not (MAINTENANCE / t).resolve().exists()]
    assert missing == []


def test_agents_md_points_to_the_maintenance_skill():
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert ".agents/skills/knowledge-maintenance/SKILL.md" in text
    assert MAINTENANCE_SKILL.is_file()
