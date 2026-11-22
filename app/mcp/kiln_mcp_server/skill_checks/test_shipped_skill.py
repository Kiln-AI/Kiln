"""Checks of the skill tree as shipped in this package, and of the
`knowledge-maintenance` skill that changes its knowledge."""

import ast
import re
from pathlib import Path

import pytest

from kiln_mcp_server.api_tool.tool import DEFAULT_BODY_LIMIT
from kiln_mcp_server.skill_checks.__main__ import run_check
from kiln_mcp_server.skill_checks.docs_index import (
    DOCS_INDEX_PATH,
    DOCS_INDEX_RULE,
    render_docs_index,
)
from kiln_mcp_server.skill_checks.knowledge_check import KNOWLEDGE_RULES, check
from kiln_mcp_server.skill_checks.knowledge_index import read_block, render_blocks
from kiln_mcp_server.skill_checks.knowledge_load import load
from kiln_mcp_server.skill_checks.knowledge_schema import (
    BUILD_COMMAND,
    COMPONENT_ROOTS,
    INDEX_BLOCKS,
    META_MODELS,
    REQUIRED_SECTIONS,
    LeverMeta,
    default_root,
)
from kiln_mcp_server.skill_checks.test_knowledge_check import API_DOC, build_tree
from kiln_mcp_server.skill_checks.tree_check import (
    SPLIT_RULE_FILE,
    TEST_SPLIT_READERS,
    TREE_RULES,
    check_tree,
    tree_paths,
)
from kiln_mcp_server.skill_files import (
    API_CATALOGUE_INDEX_PATH,
    DEFAULT_ORIGIN,
    HINT,
    ROOT_FILE,
    get_index,
    read_file,
    read_skill,
)
from kiln_mcp_server.texts import (
    PATH_DESCRIPTION,
    SKILL_TOOL_DESCRIPTION,
    WHAT_KILN_IS,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MAINTENANCE = REPO_ROOT / ".agents" / "skills" / "knowledge-maintenance"
MAINTENANCE_SKILL = MAINTENANCE / "SKILL.md"
MAX_MAINTENANCE_LINES = 500

# Rules whose problems do not fail the shipped-tree tests yet, each with the
# content batch that makes it pass (skill_and_content section 9).
PENDING_RULES: set[str] = set()

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


def test_the_generated_blocks_are_current():
    kb = load(default_root())
    rendered = render_blocks(kb)
    for index, blocks in INDEX_BLOCKS.items():
        text = read_file(index, get_index())
        for block in blocks:
            assert read_block(text, block) == rendered[(index, block)], (index, block)


# The knowledge set of Kiln Harness Tuner at the commit that the
# `knowledge-maintenance` skill records: files per component root, sub-files
# included.
IMPORTED_FILES = {"levers": 7, "techniques": 30, "smells": 15, "playbooks": 22}


def test_the_knowledge_was_imported_whole():
    tree = get_index().files
    counts = {
        kind: sum(
            1
            for key in tree
            if key.startswith(folder + "/") and key not in INDEX_BLOCKS
        )
        for kind, folder in COMPONENT_ROOTS.items()
    }
    assert counts == IMPORTED_FILES


def test_a_document_of_each_type_exists():
    kb = load(default_root())
    for kind in (*COMPONENT_ROOTS, "subfile", "index"):
        assert kb.by_kind(kind), kind


def test_every_lever_names_its_api_docs():
    for doc in load(default_root()).by_kind("levers"):
        assert isinstance(doc.meta, LeverMeta), doc.path
        assert doc.meta.api_docs, doc.path


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


# --- the split rule ------------------------------------------------------------

# The three parts of harness-tuner's split rule, and the leak rules, as
# `train_val_test.md` words them.
SPLIT_RULE_PARTS = (
    "**Tune on train.**",
    "**Confirm on val, by metrics only.**",
    "read summary numbers only",
    "**Never read test.**",
    "## An eval with only a test split",
    "## The leak rules",
)


def test_the_split_rule_file_states_the_rule():
    text = read_file(SPLIT_RULE_FILE, get_index())
    for part in SPLIT_RULE_PARTS:
        assert part in text, part
    for reader in TEST_SPLIT_READERS:
        assert reader in text, reader


def test_test_split_readers_are_endpoint_docs_or_app_links():
    tree = get_index().files
    for reader in TEST_SPLIT_READERS:
        if reader.startswith(DEFAULT_ORIGIN):
            assert reader.startswith(f"{DEFAULT_ORIGIN}/specs/"), reader
        else:
            assert reader in tree, reader


# --- the code tool wrapper templates -------------------------------------------

WRAPPER_FOLDER = "references/knowledge/code_tool_wrappers/"
WRAPPER_TEMPLATE_COUNT = 8
PYTHON_FENCE_RE = re.compile(r"^```python\n(.*?)^```$", re.DOTALL | re.MULTILINE)


def _wrapper_templates() -> dict[str, str]:
    index = get_index()
    return {
        key: read_file(key, index)
        for key in index.files
        if key.startswith(WRAPPER_FOLDER)
    }


def test_wrapper_templates_compile():
    """Each template holds one Python module that parses and defines a
    top-level `run`, the function that Kiln calls."""
    templates = _wrapper_templates()
    assert len(templates) == WRAPPER_TEMPLATE_COUNT
    for key, text in templates.items():
        blocks = PYTHON_FENCE_RE.findall(text)
        assert len(blocks) == 1, key
        module = ast.parse(blocks[0], filename=key)
        compile(module, key, "exec")
        run_functions = [
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run"
        ]
        assert len(run_functions) == 1, key


def test_wrapper_templates_are_listed_by_the_authoring_guide():
    guide = read_file("references/knowledge/code_tool_authoring.md", get_index())
    for key in _wrapper_templates():
        assert f"`{key}`" in guide, key


# --- the glue files ------------------------------------------------------------

RUN_AN_EXPERIMENT = "references/knowledge/run_an_experiment.md"
DIAGNOSE_AN_AGENT = "references/knowledge/diagnose_an_agent.md"

GLUE_FILE_PARTS = {
    RUN_AN_EXPERIMENT: (
        "Two paths",
        "Words",
        "Before you start",
        "The hypothesis",
        "Cost before you spend",
        "Build the candidate",
        "Measure on train, and judge",
        "Confirm on val",
        "Keep or discard",
        "Record and report",
        "Variants",
    ),
    DIAGNOSE_AN_AGENT: (
        "The agent as it is",
        "What the smells measure",
        "The scores on train",
        "The failing train items",
        "Where to go next",
    ),
}


def _sections(text: str) -> dict[str, str]:
    """Each `## ` section's text by heading, in order of the file."""
    sections = {}
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = part.partition("\n")
        sections[heading.strip()] = body
    return sections


@pytest.mark.parametrize("path", sorted(GLUE_FILE_PARTS))
def test_the_glue_files_have_their_parts(path):
    sections = _sections(read_file(path, get_index()))
    assert tuple(sections) == GLUE_FILE_PARTS[path]


def test_run_an_experiment_opens_with_the_two_paths():
    two_paths = _sections(read_file(RUN_AN_EXPERIMENT, get_index()))["Two paths"]
    assert "Kiln Harness Tuner" in two_paths
    assert "one-off" in two_paths


# --- SKILL.md ------------------------------------------------------------------

SKILL_MD_MAX_LINES = 300
SKILL_MD_MAX_CHARS = 20_000

# The `## ` sections of SKILL.md, in order. The text before the first one says
# what Kiln is.
SKILL_MD_PARTS = (
    "Reading skill files",
    "Routing",
    "Calling the Kiln API",
    "Working with the user",
    "Links into the app",
    "Other entry points",
    "What you cannot do over this connection",
)

MODE_PATHS = (
    "references/modes/project_operations.md",
    "references/modes/improve_task.md",
    "references/modes/learn_about_kiln.md",
    "references/modes/establish_intent.md",
)

MAIN_PAGES = tuple(
    f"{DEFAULT_ORIGIN}/{path}"
    for path in (
        "run",
        "dataset/{project_id}/{task_id}",
        "specs/{project_id}/{task_id}",
        "optimize/{project_id}/{task_id}",
        "prompts/{project_id}/{task_id}",
        "models",
        "tools/{project_id}",
        "skills/{project_id}",
        "docs/{project_id}",
        "fine_tune/{project_id}/{task_id}",
        "generate/{project_id}/{task_id}",
        "jobs",
        "settings",
    )
)

# The app pages where the user does what this connection cannot.
BLOCKED_CAPABILITY_PAGES = tuple(
    f"{DEFAULT_ORIGIN}/{path}"
    for path in (
        "settings/providers",
        "settings/providers/kiln_pro",
        "settings/import_project",
        "settings/edit_project/{project_id}",
        "settings",
        "settings/manage_projects",
        "docs/library/{project_id}/{document_id}",
        "skills/{project_id}/{skill_id}",
    )
)

# The entry points SKILL.md names beside the modes. A path is required once
# its file is in the tree.
ENTRY_POINTS = (
    "references/docs/docs_index.md",
    "references/levers/index.md",
    "references/improving_agents/index.md",
    "references/knowledge/run_an_experiment.md",
    "references/knowledge/train_val_test.md",
    "references/knowledge/memory.md",
    "references/knowledge/working_with_project_files.md",
    "references/knowledge/model_work.md",
)


def _skill_md_sections() -> tuple[str, dict[str, str]]:
    """The served SKILL.md: the text before the first `## ` heading, and each
    section's text by heading."""
    text = read_skill(None, DEFAULT_ORIGIN)
    return re.split(r"^## ", text, flags=re.M)[0], _sections(text)


def test_skill_md_has_the_required_parts():
    intro, sections = _skill_md_sections()
    assert tuple(sections) == SKILL_MD_PARTS
    assert WHAT_KILN_IS in intro
    assert "while you do Kiln work" in intro

    for path in MODE_PATHS:
        assert path in sections["Routing"], path
    assert API_CATALOGUE_INDEX_PATH in sections["Calling the Kiln API"]
    for page in MAIN_PAGES:
        assert f"`{page}`" in sections["Links into the app"], page
    tree = get_index().files
    for path in ENTRY_POINTS:
        if path in tree:
            assert path in sections["Other entry points"], path
    for page in BLOCKED_CAPABILITY_PAGES:
        assert f"`{page}`" in sections["What you cannot do over this connection"], page


def test_skill_md_size():
    text = read_file(ROOT_FILE, get_index())
    assert len(text.splitlines()) <= SKILL_MD_MAX_LINES
    assert len(text) <= SKILL_MD_MAX_CHARS


# Forms of the app address that `apply_origin` would not replace.
UNREPLACED_ADDRESS = re.compile(
    r"127\.0\.0\.1:8757|https://localhost:8757|(?<!http://)localhost:8757"
)


def test_address_replacement_covers_every_app_link():
    index = get_index()
    texts = {key: read_file(key, index) for key in index.files}
    assert any(DEFAULT_ORIGIN in text for text in texts.values())
    assert [key for key, text in texts.items() if UNREPLACED_ADDRESS.search(text)] == []


def test_docs_index_is_current():
    root = default_root()
    assert read_file(DOCS_INDEX_PATH, get_index()) == render_docs_index(root)


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
