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
from kiln_mcp_server.skill_checks.front_matter import read_front_matter
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
    SmellMeta,
    TechniqueMeta,
    default_root,
)
from kiln_mcp_server.skill_checks.test_knowledge_check import API_DOC, build_tree
from kiln_mcp_server.skill_checks.tree_check import (
    HARNESS_TUNER_RECORD_STRINGS,
    KNOWLEDGE_TREES,
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
    CALL_KILN_API_DESCRIPTION,
    PATH_DESCRIPTION,
    SERVER_INSTRUCTIONS,
    SKILL_TOOL_DESCRIPTION,
    WHAT_KILN_IS,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MAINTENANCE = REPO_ROOT / ".agents" / "skills" / "knowledge-maintenance"
MAINTENANCE_SKILL = MAINTENANCE / "SKILL.md"
MAX_MAINTENANCE_LINES = 500

# Rules whose problems do not fail the shipped-tree tests, for work that adds a
# rule before the tree meets it. `test_no_rule_is_pending` fails on any entry,
# so the set is empty whenever the suite passes.
PENDING_RULES: set[str] = set()

# Files allowed over the size limit, each with its reason.
OVER_BODY_LIMIT_ALLOWED: dict[str, str] = {}


@pytest.fixture(scope="module")
def shipped_problems():
    return check_tree(default_root())


def test_pending_rules_are_known_rules():
    assert PENDING_RULES <= {*TREE_RULES, *KNOWLEDGE_RULES, DOCS_INDEX_RULE}


def test_no_rule_is_pending():
    assert PENDING_RULES == set()


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
    assert all(counts[kind] >= IMPORTED_FILES[kind] for kind in IMPORTED_FILES), counts


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


# The texts an agent reads before the skill, and whether each must give an
# example path.
TEXTS_BEFORE_THE_SKILL = {
    "tool": (SKILL_TOOL_DESCRIPTION, True),
    "path": (PATH_DESCRIPTION, True),
    "hint": (HINT, True),
    "api_tool": (CALL_KILN_API_DESCRIPTION, True),
    "instructions": (SERVER_INSTRUCTIONS, False),
}


@pytest.mark.parametrize("name", sorted(TEXTS_BEFORE_THE_SKILL))
def test_example_paths_exist(name):
    text, needs_an_example = TEXTS_BEFORE_THE_SKILL[name]
    examples = re.findall(r"references/[A-Za-z0-9_./-]+\.md", text)
    assert bool(examples) or not needs_an_example
    assert [path for path in examples if path not in get_index().files] == []


def test_the_api_tool_names_the_catalogue_index():
    assert f"`{API_CATALOGUE_INDEX_PATH}`" in CALL_KILN_API_DESCRIPTION


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
        "A quick check",
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


HARNESS_TUNER_FIRST_LINE = (
    "If you are Kiln Harness Tuner, follow your system prompt. "
    "It has similar concepts, but better enforcement."
)


def test_run_an_experiment_opens_with_the_two_paths():
    text = read_file(RUN_AN_EXPERIMENT, get_index())
    body = read_front_matter(text).body
    assert body.strip().splitlines()[0] == HARNESS_TUNER_FIRST_LINE
    two_paths = _sections(text)["Two paths"]
    assert "Kiln Harness Tuner" in two_paths
    assert "one-off" in two_paths


# --- Kiln Harness Tuner's experiment-costing and kiln-task-setup skills --------

EXPERIMENT_COSTING = "references/knowledge/experiment_costing.md"

# The six cost lanes of Kiln Harness Tuner's experiment-costing skill, in order.
COST_LANES = (
    "Drives (target inference)",
    "Synthetic user (driver model)",
    "Judging — the lane you pay AGAIN on every re-score",
    "Third-party infrastructure (MCP calls, writes)",
    "Provider quotas and keys",
    "The replicate — the error bar is a cost lane",
)


def test_run_an_experiment_points_to_the_costing_file():
    sections = _sections(read_file(RUN_AN_EXPERIMENT, get_index()))
    assert EXPERIMENT_COSTING in sections["Cost before you spend"]


def test_the_costing_file_has_every_cost_lane_and_the_human_gate():
    sections = _sections(read_file(EXPERIMENT_COSTING, get_index()))
    lanes = sections["The six cost lanes — price every one, every time"]
    positions = [lanes.index(f"**{lane}.**") for lane in COST_LANES]
    assert positions == sorted(positions)
    assert "**Human gate.**" in sections["Rules"]


def test_the_costing_file_reads_synthetic_user_usage_off_the_task_run():
    text = " ".join(read_file(EXPERIMENT_COSTING, get_index()).split())
    assert "EvalRun.synthetic_user_usage" not in text
    assert "TaskRun.synthetic_user_usage" in text
    assert "scored_run_id" in text
    # Kiln rejects a custom score on an eval (`EvalOutputScore`).
    assert "custom`-score" not in text


# Facts of Kiln Harness Tuner's kiln-task-setup skill, each with the file that
# holds it.
TASK_SETUP_FACTS = (
    (
        "references/knowledge/create_task.md",
        "**`turn_mode` is frozen**: PATCH rejects changes",
    ),
    (
        "references/knowledge/tools.md",
        "**The built-in `kiln_tool::call_kiln_api` is hidden from UI tool pickers**",
    ),
    (
        "references/knowledge/model_create_configs.md",
        "Require `supports_function_calling: true` for tool-bearing tasks.",
    ),
)


@pytest.mark.parametrize(("path", "phrase"), TASK_SETUP_FACTS)
def test_the_named_task_setup_facts_are_in_their_files(path, phrase):
    assert phrase in " ".join(read_file(path, get_index()).split())


# --- memory: the records Kiln Harness Tuner's code writes ---------------------

MEMORY = "references/knowledge/memory.md"
MEMORY_FORMATS = "references/knowledge/memory_formats/"

# The strings Kiln Harness Tuner's code writes and parses back, by the file
# that lists them for readers. The source is its `memory_schema.py` and
# `memory.py` at b49f159, as section 3 of
# `specs/projects/kiln_mcp_server/research/harness_tuner_alignment_audit/contract.md`
# lists them. Placeholders in `<>` stand for the values its code fills in.
HARNESS_TUNER_FORMATS: dict[str, tuple[str, ...]] = {
    "experiment_records.md": (
        "EXP <MMDD>-w<k>-<n>",
        "EXP <id> (<technique>): <hypothesis> — RUNNING",
        " — REFUTED",
        " — FAILED (infra: <error class>)",
        " — ABANDONED (<why>)",
        " — DEAD END (<why>)",
        " — NOT LANDED (<detail>)",
        "`<k>/<n> targets fixed`",
        "`<k>/<n> fixed, <b>/<g> guards broke`",
        "`stopped at n=<n> by <rule>: <numbers>`",
        "`capped at <n> items: …`",
        " — CAPPED (<detail>)",
        # Kiln Harness Tuner writes a minus sign (U+2212) here, not a hyphen.
        "`capped at $<x> after <n> items: inconclusive — net +<a>/\u2212<b> so far`",
        "`capped at $<x> after <n> items: inconclusive — lost <k> of <n> baseline passes so far`",
        "`capped by the run budget ($<x> left) after <n> items: …`",
        " — PROMOTED <MM-DD>",
        " — REJECTED AT VAL <MM-DD>",
        " — HELD (constraint <id>) <MM-DD>",
        "- ingredient: <memory id> (rc <run config id>)",
        "- rejected at the val gate <MM-DD> vs baseline <run config id> — ",
        "passed over: not promoted; rc <run config id> was promoted instead.",
        "an eval dropped at val: down beyond doubt on eval ",
        "no gain at val: no targeted eval improved.",
        "a gain at val, not clear: a targeted eval improved, but not beyond doubt.",
        "not promoted at val; details in the run report.",
        "— did not beat it; details in the run report.",
        "- held at the val gate <MM-DD> on OPEN constraint <id> — not judged on its numbers; resubmit this rc unchanged (existing_rc_id) once answered.",
        "- blocked at the val gate <MM-DD>: ",
        "residual gate: <summary> (needed <required>; seed <seed>)",
        "residual still failing: ",
        "residual guards broke: ",
        "`bundle cost`",
        *(
            f"`{key}`"
            for key in (
                "hypothesis",
                "predicted effect",
                "parent rc",
                "eval",
                "issue",
                "technique",
                "head_to_head_group",
                "reused rc",
                "wildcard",
                "merge of",
                "conflict flags",
                "rc",
                "change",
                "generality",
                "judge copy",
                "reference check",
            )
        ),
    ),
    "issue_records.md": (
        "[<STATE>: ]issue: <one line>",
        "`UNMEASURED: `",
        "`UNMEASURABLE: `",
        "`FIXED: `",
        "`WONT_FIX: `",
        "eval: <eval id> (<eval name>, <config kind>)",
        "priority: p<n> (source: spec <spec id>)",
        "status: <state> at sync · fp: <hex> · synced <YYYY-MM-DD>",
        "- eval: <eval id> (built <MM-DD>, reproduced)",
        "- eval: <eval id> (linked by kiln-harness-tuner setup <MM-DD>)",
        "- fixed <MM-DD> by <citation>",
        "- reopened when promoting baseline <run config id>. Issue repros on <run config id>.",
        "`smell`",
        "`smell_<smell id>`",
        "`baseline_audit`",
        "`baseline_judge_copy`",
        "`audited_rc_<run config id>`",
    ),
    "open_questions.md": (
        "OPEN: <question>",
        "question: ",
        "default: ",
        "gates: ",
        "source: assumption",
        "re-ask when: ",
        "`human`",
    ),
    "baseline_and_val_records.md": (
        "`rc_<run config id>`",
        "Validation metrics for each baseline promotion (val-grade; the numbers are in content, never here)",
        "<new run config id> (<MM-DD>, <EXP label>) ← <old run config id> — <rationale>",
    ),
    "screening_and_probe_records.md": (
        "SCREEN SURVIVOR: <label> — <passed>/<judged> vs baseline <b>",
        "SCREEN SURVIVOR: <label> — lost <k> of <n> baseline passes, no loss rate above <X>% at 95%",
        "SCREEN DEAD END: <label> — <reason>",
        "SCREEN CAPPED: <label> — ",
        "PROBE <item>: <question> → YES",
        "`→ NO`",
        "`→ UNCLEAR`",
        "`probe`",
        "`screen`",
        *(
            f"`{key}`"
            for key in (
                "candidate",
                "run config",
                "label",
                "overrides",
                "parent rc",
                "round",
                "round no",
                "items",
                "screened on evals",
                "verdict",
                "reason",
                "quality",
                "measured",
                "run",
                "date",
                "baseline rc",
                "result",
                "question",
                "answer",
                "method",
                "evidence",
                "drives",
                "ephemeral rcs",
                "for idea",
                "notes",
            )
        ),
    ),
}

# Matched by Kiln Harness Tuner's code as a whole line.
SETUP_DELIMITER = "— setup wrote everything above; lines below belong to the loop —"


def _memory_format_files() -> list[str]:
    return sorted(key for key in get_index().files if key.startswith(MEMORY_FORMATS))


def test_the_memory_formats_are_one_file_each():
    assert _memory_format_files() == sorted(
        MEMORY_FORMATS + name for name in HARNESS_TUNER_FORMATS
    )


@pytest.mark.parametrize("name", sorted(HARNESS_TUNER_FORMATS))
def test_memory_lists_harness_tuner_formats(name):
    text = read_file(MEMORY_FORMATS + name, get_index())
    assert "Kiln Harness Tuner's code" in text
    missing = [string for string in HARNESS_TUNER_FORMATS[name] if string not in text]
    assert missing == []


@pytest.mark.parametrize("name", sorted(HARNESS_TUNER_FORMATS))
def test_each_memory_format_file_says_it_is_read_only(name):
    front = read_front_matter(read_file(MEMORY_FORMATS + name, get_index()))
    assert str(front.data["description"]).startswith("Read-only")
    assert "so that you can read" in " ".join(front.body.split())


def test_the_setup_delimiter_is_on_a_line_of_its_own():
    text = read_file(MEMORY_FORMATS + "issue_records.md", get_index())
    assert SETUP_DELIMITER in text.splitlines()


def test_memory_names_each_format_file():
    # The skill tool cannot list a folder, so each file is named by its path.
    formats = _sections(read_file(MEMORY, get_index()))[
        "The formats that Kiln Harness Tuner writes"
    ]
    for key in _memory_format_files():
        assert f"`{key}`" in formats, key


# The rules of Kiln Harness Tuner's `memory/SKILL.md` at b49f159 that a
# rewrite once lost, each as a phrase of its port.
MEMORY_RULES = (
    # A failed write: the return field, once, a summary, exempt from budgets.
    "disclose it in your return",
    "A disclosure rides **once**",
    "exempt from any length budget on that field",
    "In a chat with a user: tell the user the finding once.",
    # A missing eval: the loop's path, then the chat case.
    "the loop's `eval_only` item build the eval and bind the issue via `link_eval`",
    "It never guesses a binding.",
    "build it only when the user agrees (`references/knowledge/create_spec.md`)",
    # Priorities.
    "`p2` — real but minor; picked up when nothing above it remains.",
    "no intent to work it in this project",
    "Priority tags are **never removed**, even on close",
    "priority is **source-owned**",
    # Experiments and dead ends.
    "small n gives direction, never validation",
    "merge-eligible wins = verdicts since the last promotion without `— PROMOTED`",
    "citing the experiment id; in a chat with a user, where no experiment record is written, the run config ids",
    # The train-side read rules.
    "Kiln Harness Tuner train-side loop agents skip this read",
    "⛔ **Never on a train-side lane**",
    # Who writes a hypothesis.
    "No agent writes one: Kiln Harness Tuner's code records each hypothesis in its experiment record",
)


@pytest.mark.parametrize("phrase", MEMORY_RULES)
def test_memory_keeps_harness_tuners_rules(phrase):
    assert phrase in " ".join(read_file(MEMORY, get_index()).split())


def test_the_baseline_record_says_how_it_is_seeded():
    text = " ".join(
        read_file(MEMORY_FORMATS + "baseline_and_val_records.md", get_index()).split()
    )
    for phrase in (
        "the task's `default_run_config_id` if it has one, else the most recently created rc",
        "zero run configs is an instructive fatal",
        "the loop never sets the human-facing `default` rc flag",
    ):
        assert phrase in text, phrase


# The call and retry discipline of Kiln Harness Tuner's `kiln-api/SKILL.md`.
API_RULES = (
    "These rules apply if you have the `call_kiln_api` tool. If you do not, you need not read them.",
    "Take them from the catalogue row exactly as printed",
    "Do not guess a body from an endpoint's name.",
    "One extra read costs less than one wrong call.",
    "Filter every call down to the fields you actually need",
    "Never write `.items[]` unless the documented shape has that key.",
    "A failed call is a **reading** problem, not a phrasing problem.",
    "an aggregate snapshot is not the full entity list",
    "A retry without that cite is a violation",
    "A second guess from memory is banned, and so is abandoning this tool for a shell after one failure.",
)


@pytest.mark.parametrize("phrase", API_RULES)
def test_the_api_rules_keep_harness_tuners_discipline(phrase):
    section = _sections(read_file(ROOT_FILE, get_index()))["Calling the Kiln API"]
    assert phrase in " ".join(section.split())


CODE_TOOL_AUTHORING = "references/knowledge/code_tool_authoring.md"
# The sections of Kiln Harness Tuner's code-tool-authoring skill, in its
# order, with the Kiln names of the ones that named its gateway or roles.
CODE_TOOL_AUTHORING_PARTS = (
    "When the tool lever is the right lever",
    "What you can build",
    "Wrapper templates — bake it into code first",
    "The one hard rule: allowlist hygiene",
    "Prerequisites",
    "Contract",
    "The calls",
    "Build discipline (the experiment deltas)",
    "Worked example — a composite wrapper, complete",
    "Related",
    "See also",
)


def test_the_authoring_guide_keeps_harness_tuners_sections():
    text = read_file(CODE_TOOL_AUTHORING, get_index())
    assert tuple(_sections(text)) == CODE_TOOL_AUTHORING_PARTS
    (example,) = PYTHON_FENCE_RE.findall(_sections(text)[CODE_TOOL_AUTHORING_PARTS[8]])
    module = ast.parse(example)
    assert [node.name for node in module.body if isinstance(node, ast.FunctionDef)] == [
        "_parse",
        "run",
    ]


# --- the glue files: no branch, no write of a code-owned record ---------------

# The knowledge trees are left out: they are the knowledge, not glue.
NOT_GLUE = (
    "references/levers/",
    "references/improving_agents/",
    "references/knowledge/api_docs/",
    "references/docs/",
)
HARNESS_TUNER_BRANCHES = ("applies when running", "when running Kiln Harness Tuner")


def test_glue_files_have_no_harness_tuner_branch():
    index = get_index()
    hits = [
        (key, phrase)
        for key in index.files
        if key.endswith(".md") and not key.startswith(NOT_GLUE)
        for phrase in HARNESS_TUNER_BRANCHES
        if phrase in " ".join(read_file(key, index).split())
    ]
    assert hits == []


def test_the_knowledge_trees_have_no_harness_tuner_branch():
    index = get_index()
    hits = [
        (key, phrase)
        for key in index.files
        if key.startswith(KNOWLEDGE_TREES)
        for phrase in HARNESS_TUNER_BRANCHES
        if phrase in " ".join(read_file(key, index).split())
    ]
    assert hits == []


IMPROVING_AGENTS_INDEX = "references/improving_agents/index.md"


def test_the_index_explains_harness_tuner_words_to_mcp_agents():
    section = _sections(read_file(IMPROVING_AGENTS_INDEX, get_index()))[
        "How to read these documents over MCP"
    ]
    assert RUN_AN_EXPERIMENT in section
    assert MEMORY in section


TRAIN_WINS_PLAYBOOK = (
    "references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md"
)


def test_the_record_strings_in_the_knowledge_are_harness_tuner_formats():
    # Each quoted record line matches a format up to its first placeholder,
    # because the playbook abbreviates the placeholder names.
    formats = [
        string for strings in HARNESS_TUNER_FORMATS.values() for string in strings
    ]
    text = " ".join(read_file(TRAIN_WINS_PLAYBOOK, get_index()).split())
    quoted = re.findall(
        r"`((?:— |- |passed over: |an eval dropped at val: |no gain at val: "
        r"|a gain at val, not clear: |not promoted at val; )[^`]+)`",
        text,
    )
    assert len(quoted) >= 10
    for line in quoted:
        prefix = line.split("<")[0]
        assert any(prefix in string for string in formats), line


def test_the_record_strings_exempt_from_banned_terms_are_harness_tuner_formats():
    formats = [
        string for strings in HARNESS_TUNER_FORMATS.values() for string in strings
    ]
    for record in HARNESS_TUNER_RECORD_STRINGS:
        assert any(record in string for string in formats), record


CODE_OWNED_WRITES = (
    "and write the `baseline` record",
    "Update the `baseline` record",
    "ending `— RUNNING`",
    "as an `experiment` memory",
    "Close the target issue with `FIXED: `",
    "in the `OPEN: ` record",
    "One record per experiment",
    "record each finding",
    "record each answer",
    "follow the formats below exactly",
    "offer to make it their new default",
)
WRITERS_OF_RECORDS = (
    ROOT_FILE,
    RUN_AN_EXPERIMENT,
    MEMORY,
    "references/modes/improve_task.md",
    "references/knowledge/local_private_on_prem.md",
)


@pytest.mark.parametrize("path", WRITERS_OF_RECORDS)
def test_glue_files_do_not_write_code_owned_records(path):
    text = " ".join(read_file(path, get_index()).split())
    assert [phrase for phrase in CODE_OWNED_WRITES if phrase in text] == []


# --- the overlap groups --------------------------------------------------------

_K = "references/knowledge/"
_L = "references/levers/"
_P = "references/improving_agents/playbooks/"
_S = "references/improving_agents/smells/"
_T = "references/improving_agents/techniques/"

_KNOWLEDGE = load(default_root())

PROMPT_DOCUMENTS = (
    f"{_L}prompt.md",
    f"{_T}add-the-missing-requirement.md",
    f"{_T}one-general-rule-per-edit.md",
    f"{_T}structure-a-long-prompt.md",
    f"{_T}policy-as-step-by-step-procedures.md",
    f"{_T}state-the-output-contract.md",
    f"{_T}decline-rules-paragraph.md",
    f"{_T}prune-one-group-at-a-time.md",
    f"{_S}very-long-prompt.md",
    f"{_P}requirement-missing-from-the-prompt.md",
    f"{_P}lost-in-long-instructions.md",
    f"{_P}wrong-scope-or-refusal.md",
    f"{_P}change-the-surface-not-the-words.md",
)
SKILL_DOCUMENTS = (
    f"{_L}skill.md",
    f"{_T}long-prompt-into-a-skill.md",
    f"{_T}document-into-a-skill.md",
    f"{_T}guide-skill-for-a-tool-set.md",
    f"{_T}rewrite-an-inherited-skill.md",
    f"{_T}skill-into-the-prompt.md",
    f"{_S}one-file-skill-with-many-topics.md",
    f"{_S}skill-too-small-to-earn-its-place.md",
    f"{_S}very-long-skill-description.md",
    f"{_S}faulty-inherited-skill.md",
    f"{_P}skill-is-not-read.md",
)
RAG_DOCUMENTS = (
    f"{_P}answers-not-grounded.md",
    f"{_T}attach-the-knowledge-source.md",
    f"{_T}answer-only-from-the-source.md",
    f"{_T}document-into-a-skill.md",
    f"{_S}document-behind-a-lookup-tool.md",
)


def _cheaper_or_faster_documents() -> tuple[str, ...]:
    """The playbook, then the techniques it links."""
    playbook = f"{_P}cheaper-or-faster.md"
    [document] = [d for d in _KNOWLEDGE.documents if d.path == playbook]
    techniques = {
        link.resolved
        for link in document.links
        if link.resolved is not None and link.resolved.startswith(_T)
    }
    return (playbook, *sorted(techniques))


def _tool_documents() -> tuple[str, ...]:
    """The tool levers and playbooks, then the techniques whose levers include
    `tool_config` or `new_tool` and the smells that apply to `tools`, except
    the documents of the prompt, skill and RAG groups."""
    taken = {*PROMPT_DOCUMENTS, *SKILL_DOCUMENTS, *RAG_DOCUMENTS}
    techniques = sorted(
        d.path
        for d in _KNOWLEDGE.by_kind("techniques")
        if isinstance(d.meta, TechniqueMeta)
        and {"tool_config", "new_tool"} & set(d.meta.levers)
        and d.path not in taken
    )
    smells = sorted(
        d.path
        for d in _KNOWLEDGE.by_kind("smells")
        if isinstance(d.meta, SmellMeta)
        and isinstance(d.meta.applies_to, list)
        and "tools" in d.meta.applies_to
        and d.path not in taken
    )
    return (
        f"{_L}tool_config.md",
        f"{_L}new_tool.md",
        f"{_P}fit-the-tool-layer-to-the-agent.md",
        f"{_P}wrong-tool-chosen.md",
        f"{_P}failure-at-a-tool-call.md",
        f"{_P}malformed-tool-calls.md",
        f"{_P}missing-context-the-agent-could-be-given.md",
        *techniques,
        *smells,
    )


ALL_LEVERS = tuple(sorted(d.path for d in _KNOWLEDGE.by_kind("levers")))

# The overlap groups of skill_and_content 9.1, in its order: the knowledge
# documents of each subject, then the Assistant files that teach it. Groups 7,
# 10 and 12 are built from the tree by the rules of 9.1, so a new document
# that belongs to one of them fails `test_each_overlap_file_has_its_see_also_line`
# until the "See also" lines name it.
OVERLAP_GROUPS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (  # 1 the order of an improvement
        (
            f"{_P}know-the-agent-before-you-plan.md",
            f"{_P}ordering-work.md",
            f"{_P}spending-the-budget.md",
        ),
        ("references/modes/improve_task.md",),
    ),
    (  # 2 measuring and judging a change
        (
            f"{_P}dealing-with-a-noisy-eval.md",
            f"{_P}dealing-with-train-wins-rejected-at-val.md",
            f"{_P}spending-the-budget.md",
        ),
        (f"{_K}eval_scores.md", f"{_K}benchmark_eval_inputs.md"),
    ),
    (  # 3 improving a prompt
        PROMPT_DOCUMENTS,
        (f"{_K}prompt_audit.md", f"{_K}prompt_rewrite.md"),
    ),
    (  # 4 model choice
        (
            f"{_L}model.md",
            f"{_T}model-swap-inside-a-class.md",
            f"{_T}faster-provider-for-the-same-model.md",
            f"{_S}old-model.md",
            f"{_P}dealing-with-an-eval-near-zero.md",
        ),
        (f"{_K}model_work.md",),
    ),
    (  # 5 run parameters
        (f"{_L}params.md", f"{_T}thinking-level-ladder.md"),
        (f"{_K}model_create_configs.md",),
    ),
    (  # 6 structured output mode
        (
            f"{_L}output_mode.md",
            f"{_P}output-contract-not-met.md",
            f"{_T}state-the-output-contract.md",
        ),
        (f"{_K}model_create_configs.md",),
    ),
    (  # 7 cheaper or faster as a goal
        _cheaper_or_faster_documents(),
        (f"{_K}model_work.md",),
    ),
    (  # 8 an eval that is itself the problem
        (
            f"{_P}dealing-with-a-wrong-eval.md",
            f"{_P}dealing-with-a-saturated-eval.md",
            f"{_P}dealing-with-a-noisy-eval.md",
            f"{_P}dealing-with-an-eval-near-zero.md",
        ),
        (
            f"{_K}specs_and_evals.md",
            f"{_K}create_spec.md",
            f"{_K}judge_types.md",
            f"{_K}eval_scores.md",
        ),
    ),
    (  # 9 skills
        SKILL_DOCUMENTS,
        (f"{_K}adding_skills.md",),
    ),
    (  # 10 tools and code tools
        _tool_documents(),
        (
            f"{_K}tools.md",
            f"{_K}code_tools.md",
            f"{_K}code_tool_authoring.md",
            f"{_K}subagents.md",
        ),
    ),
    (  # 11 grounding and RAG
        RAG_DOCUMENTS,
        (f"{_K}rag.md",),
    ),
    (  # 12 creating a task and a run config
        ALL_LEVERS,
        (f"{_K}create_task.md", f"{_K}model_create_configs.md"),
    ),
    (  # 13 restrictions, local and private models
        (f"{_P}working-inside-restrictions.md",),
        (f"{_K}local_private_on_prem.md",),
    ),
    (  # 14 fine-tunes
        (f"{_T}model-swap-inside-a-class.md", f"{_L}model.md"),
        (f"{_K}fine_tuning.md",),
    ),
    (  # 15 a classifier on a decision model
        (f"{_T}decision-model-for-a-classifier.md",),
        (f"{_K}typesafe_jev.md",),
    ),
)

SEE_ALSO_LEAD = "When and why, in the knowledge: "


def see_also_paths() -> dict[str, tuple[str, ...]]:
    """For each Assistant file of a group, the paths of its "See also" line:
    the knowledge documents of its groups, in group order, each once."""
    paths: dict[str, dict[str, None]] = {}
    for documents, files in OVERLAP_GROUPS:
        for file in files:
            paths.setdefault(file, {}).update(dict.fromkeys(documents))
    return {file: tuple(documents) for file, documents in paths.items()}


def see_also_line(paths: tuple[str, ...]) -> str:
    return SEE_ALSO_LEAD + ", ".join(f"`{path}`" for path in paths) + "."


def test_the_overlap_groups_name_files_of_the_tree():
    tree = get_index().files
    for documents, files in OVERLAP_GROUPS:
        assert [path for path in (*documents, *files) if path not in tree] == []


@pytest.mark.parametrize("path", sorted(see_also_paths()))
def test_each_overlap_file_has_its_see_also_line(path):
    text = read_file(path, get_index())
    assert text.count("\n## See also\n") == 1
    assert _sections(text)["See also"].strip() == see_also_line(see_also_paths()[path])


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
        "settings/trust_code/{project_id}",
    )
)

# The entry points SKILL.md names beside the modes. A path is required once
# its file is in the tree.
ENTRY_POINTS = (
    "references/docs/docs_index.md",
    "references/levers/index.md",
    "references/improving_agents/index.md",
    "references/knowledge/run_an_experiment.md",
    "references/knowledge/experiment_costing.md",
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
