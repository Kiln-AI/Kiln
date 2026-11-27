import pytest

from kiln_mcp_server.conftest import write_tree
from kiln_mcp_server.skill_checks.knowledge_schema import Problem
from kiln_mcp_server.skill_checks.tree_check import (
    SPLIT_RULE_FILE,
    TREE_RULES,
    PathRef,
    check_tree,
    paths_in,
    tree_paths,
)

SKILL_MD = """---
name: kiln
description: Work with Kiln.
---

# Kiln

Modes: `references/client_guidance/chat/learn.md`.
Knowledge: [RAG](references/knowledge/rag.md).
API: start from `references/knowledge/api_docs/api_index.md`.
Help: references/docs/ (the help articles).
"""

LEARN_MD = """---
name: learn
description: Learn about Kiln.
---

Open http://localhost:8757/specs/{project_id}/{task_id}.
"""

RAG_MD = """---
name: rag
description: RAG in Kiln.
---

Call `GET /api/projects/{project_id}/rag_configs`.
"""

API_INDEX = """# Kiln API catalogues

| Catalogue | Area | Endpoints | What it covers |
|---|---|---|---|
| `references/knowledge/api_docs/projects_api_list.md` | Projects | 1 | Projects. |
"""

CATALOGUE = """# Projects API

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects`|GET|List Projects|A \\| pipe.|get_api_projects.md|
"""

DOCS_README = """---
online_url: https://docs.kiln.tech/docs/
---

# Docs

See [Evals](references/docs/evals.md).
"""

EVALS_ARTICLE = """---
description: Evals.
online_url: https://docs.kiln.tech/docs/evals
---

# Evals
"""

CLEAN_TREE = {
    "SKILL.md": SKILL_MD,
    "references/client_guidance/chat/learn.md": LEARN_MD,
    "references/knowledge/rag.md": RAG_MD,
    "references/knowledge/api_docs/api_index.md": API_INDEX,
    "references/knowledge/api_docs/projects_api_list.md": CATALOGUE,
    "references/knowledge/api_docs/get_api_projects.md": "# List Projects\n",
    "references/docs/README.md": DOCS_README,
    "references/docs/evals.md": EVALS_ARTICLE,
}


def problems_of(tmp_path, changes: dict[str, str | None], **kwargs) -> list[Problem]:
    tree = {**CLEAN_TREE, **changes}
    files = {key: text for key, text in tree.items() if text is not None}
    return check_tree(write_tree(tmp_path / "skill", files), **kwargs)


def rules_of(problems: list[Problem]) -> set[tuple[str, str]]:
    return {(problem.rule, problem.path) for problem in problems}


def with_line(text: str, line: str) -> str:
    return text + line + "\n"


def test_a_clean_tree_has_no_problem(tmp_path):
    assert problems_of(tmp_path, {}) == []


def test_tree_paths_skips_hidden_files(tmp_path):
    root = write_tree(tmp_path / "skill", {**CLEAN_TREE, "references/.DS_Store": "x"})
    assert tree_paths(root) == frozenset(CLEAN_TREE)


def test_unresolved_path_fails(tmp_path):
    problems = problems_of(
        tmp_path,
        {"SKILL.md": with_line(SKILL_MD, "Read `references/knowledge/nope.md`.")},
    )
    assert problems == [
        Problem(
            "tree-path",
            "SKILL.md",
            "line 12: `references/knowledge/nope.md` is not a file or folder of the skill",
        )
    ]


def test_wrong_case_path_fails(tmp_path):
    problems = problems_of(
        tmp_path, {"SKILL.md": with_line(SKILL_MD, "See references/knowledge/RAG.md.")}
    )
    assert rules_of(problems) == {("tree-path", "SKILL.md")}
    assert "did you mean `references/knowledge/rag.md`?" in problems[0].message


@pytest.mark.parametrize(
    "link",
    [
        "[x](./references/knowledge/rag.md)",
        "[x](../rag.md)",
        "[x](rag.md)",
        "[x](rag.md#setup)",
        "[x](/references/knowledge/rag.md)",
        "[x](/SKILL.md)",
        "[x](knowledge/rag.md)",
        "[x](modes/learn.md#top)",
        "Read `/references/knowledge/rag.md`.",
        "Read `/SKILL.md`.",
        "Read /references/knowledge/rag.md first.",
        "Read `../references/nope.md`.",
        "Read `./references/client_guidance/chat/learn.md`.",
        "Read `./SKILL.md`.",
        "Then see ../references/nope.md for more.",
        "Then see ./references/knowledge/rag.md.",
    ],
)
def test_relative_link_fails(tmp_path, link):
    problems = problems_of(
        tmp_path, {"references/knowledge/rag.md": with_line(RAG_MD, link)}
    )
    assert ("tree-relative", "references/knowledge/rag.md") in rules_of(problems)


def test_a_relative_path_is_one_problem(tmp_path):
    line = "[x](/references/knowledge/nope.md) and `/references/knowledge/rag.md`."
    problems = problems_of(tmp_path, {"SKILL.md": with_line(SKILL_MD, line)})
    assert [p.message for p in problems] == [
        "line 12: `/references/knowledge/nope.md` is not a full path from the skill root; write it as `references/...`, with no leading `/`, `./` or `../`",
        "line 12: `/references/knowledge/rag.md` is not a full path from the skill root; write it as `references/...`, with no leading `/`, `./` or `../`",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "[docs](https://docs.kiln.tech/docs/evals.md)",
        "See http://localhost:8757/references/x.md and `/api/references/x.md`.",
        "[Kiln](SKILL.md) and [app](/settings).",
    ],
)
def test_urls_and_app_paths_are_not_relative_paths(tmp_path, text):
    problems = problems_of(tmp_path, {"SKILL.md": with_line(SKILL_MD, text)})
    assert "tree-relative" not in {p.rule for p in problems}


def test_bare_name_fails(tmp_path):
    lines = "Read rag.md first.\nThen `learn.md` and api_index.md."
    problems = problems_of(tmp_path, {"SKILL.md": with_line(SKILL_MD, lines)})
    assert [problem.message for problem in problems] == [
        "line 13: `learn.md` is a bare file name; write the full path `references/client_guidance/chat/learn.md`",
        "line 12: `rag.md` is a bare file name; write the full path `references/knowledge/rag.md`",
        "line 13: `api_index.md` is a bare file name; write the full path `references/knowledge/api_docs/api_index.md`",
    ]


def test_bare_name_in_link_label_passes(tmp_path):
    line = "[rag.md](references/knowledge/rag.md) and [`learn.md`](references/client_guidance/chat/learn.md)"
    assert problems_of(tmp_path, {"SKILL.md": with_line(SKILL_MD, line)}) == []


def test_a_name_that_is_not_unique_is_not_a_bare_name(tmp_path):
    changes = {
        "references/knowledge/README.md": "---\nname: README\ndescription: Knowledge.\n---\n",
        "SKILL.md": with_line(
            SKILL_MD, "Read `references/knowledge/`, its README.md, and SKILL.md."
        ),
    }
    assert problems_of(tmp_path, changes) == []


def test_catalogue_bare_name_resolves(tmp_path):
    changes = {
        "references/knowledge/api_docs/projects_api_list.md": CATALOGUE.replace(
            "get_api_projects.md", "get_api_nope.md"
        )
    }
    assert rules_of(problems_of(tmp_path, changes)) == {
        ("tree-path", "references/knowledge/api_docs/projects_api_list.md"),
        ("tree-unreachable", "references/knowledge/api_docs/get_api_projects.md"),
    }


def test_catalogue_names_are_paths():
    tree = frozenset(CLEAN_TREE)
    refs = paths_in(
        CATALOGUE, file="references/knowledge/api_docs/projects_api_list.md", tree=tree
    )
    assert refs == [
        PathRef(
            5,
            "get_api_projects.md",
            "references/knowledge/api_docs/get_api_projects.md",
            False,
            "catalogue",
        )
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Read `references/knowledge/{name}.md`.",
        "Read references/knowledge/{name}.md.",
        "Read references/levers/*.md.",
        "Read `references/knowledge/<file>.md`.",
        "Read `references/knowledge/X.md`.",
        "Read [the guide](<name>.md).",
        "Read [the guide](references/knowledge/{name}.md).",
    ],
)
def test_placeholder_is_skipped(tmp_path, line):
    assert problems_of(tmp_path, {"SKILL.md": with_line(SKILL_MD, line)}) == []


def test_an_angle_bracket_link_target_is_a_reference(tmp_path):
    line = "[RAG](<references/knowledge/rag.md>) and [gone](<references/knowledge/nope.md>)."
    problems = problems_of(tmp_path, {"SKILL.md": with_line(SKILL_MD, line)})
    assert [p.message for p in problems] == [
        "line 12: `references/knowledge/nope.md` is not a file or folder of the skill"
    ]


def test_ignored_refs_are_skipped(tmp_path):
    article = """---
online_url: https://docs.kiln.tech/docs/skills
---

A skill can hold `references/STYLE_GUIDE.md` and references/API_RESPONSE_FORMAT.md.
"""
    changes = {
        "references/docs/skills.md": article,
        "references/docs/README.md": with_line(
            DOCS_README, "[Skills](references/docs/skills.md)"
        ),
    }
    assert problems_of(tmp_path, changes) == []
    moved = {**changes, "references/docs/other.md": article.replace("skills", "other")}
    moved["references/docs/README.md"] += "[Other](references/docs/other.md)\n"
    assert {p.rule for p in problems_of(tmp_path, moved)} == {"tree-path"}


def test_path_in_fence_is_checked(tmp_path):
    fence = '```\npath = "references/knowledge/nope.md"\n```'
    problems = problems_of(tmp_path, {"SKILL.md": with_line(SKILL_MD, fence)})
    assert rules_of(problems) == {("tree-path", "SKILL.md")}


def test_anchor_and_folder_links_resolve(tmp_path):
    lines = (
        "[RAG setup](references/knowledge/rag.md#setup), [top](#kiln), "
        "[docs](references/docs/), `references/knowledge/api_docs/`, "
        "[web](https://docs.kiln.tech/docs/evals)."
    )
    changes = {
        "SKILL.md": SKILL_MD.replace(
            "Help: references/docs/ (the help articles).\n", ""
        )
        + lines
        + "\n"
    }
    assert problems_of(tmp_path, changes) == []


def test_folder_link_reaches_its_readme_only(tmp_path):
    changes = {
        "SKILL.md": SKILL_MD.replace(
            "Help: references/docs/ (the help articles).\n", ""
        )
    }
    assert rules_of(problems_of(tmp_path, changes)) == {
        ("tree-unreachable", "references/docs/README.md"),
        ("tree-unreachable", "references/docs/evals.md"),
    }


@pytest.mark.parametrize(
    "text", ['Call skill(name="kiln").', "Use the kiln_skill tool."]
)
def test_call_syntax_fails(tmp_path, text):
    problems = problems_of(
        tmp_path,
        {"references/client_guidance/chat/learn.md": with_line(LEARN_MD, text)},
    )
    assert rules_of(problems) == {
        ("tree-call-syntax", "references/client_guidance/chat/learn.md")
    }


def test_skill_md_may_name_the_skill_tool(tmp_path):
    problems = problems_of(
        tmp_path,
        {"SKILL.md": with_line(SKILL_MD, 'Call kiln_skill(path="SKILL.md").')},
    )
    assert ("tree-call-syntax", "SKILL.md") not in rules_of(problems)


def test_skill_md_may_not_use_the_old_call_syntax(tmp_path):
    problems = problems_of(
        tmp_path, {"SKILL.md": with_line(SKILL_MD, 'Call skill(name="kiln").')}
    )
    assert ("tree-call-syntax", "SKILL.md") in rules_of(problems)


@pytest.mark.parametrize(
    "text",
    [
        "Open `/specs/{project_id}/{task_id}`.",
        "Open [the settings](/settings).",
        "Open `/run?task=1`.",
    ],
)
def test_app_path_without_origin_fails(tmp_path, text):
    problems = problems_of(
        tmp_path, {"references/knowledge/rag.md": with_line(RAG_MD, text)}
    )
    assert rules_of(problems) == {("tree-app-link", "references/knowledge/rag.md")}


def test_app_path_rule_skips_help_articles_and_api_docs(tmp_path):
    changes = {
        "references/docs/evals.md": with_line(EVALS_ARTICLE, "Open `/specs`."),
        "references/knowledge/api_docs/get_api_projects.md": "# List\n\nSee `/settings`.\n",
    }
    assert problems_of(tmp_path, changes) == []


@pytest.mark.parametrize(
    "text",
    ["Call `/api/settings`.", "Open `/specsheet`.", "`http://localhost:8757/specs`"],
)
def test_api_path_is_not_an_app_link(tmp_path, text):
    assert (
        problems_of(tmp_path, {"references/knowledge/rag.md": with_line(RAG_MD, text)})
        == []
    )


@pytest.mark.parametrize(
    "folder",
    [
        "references/client_guidance/chat",
        "references/levers",
        "references/improving_agents",
    ],
)
def test_split_wording_needs_the_pointer(tmp_path, folder):
    key = (
        f"{folder}/learn.md"
        if folder == "references/client_guidance/chat"
        else f"{folder}/index.md"
    )
    body = "Confirm on the val split.\nKeep a held-out set."
    text = LEARN_MD if folder == "references/client_guidance/chat" else "# Index\n"
    changes = {key: with_line(text, body), "SKILL.md": with_line(SKILL_MD, f"`{key}`")}
    problems = problems_of(tmp_path, changes)
    assert [(p.rule, p.path) for p in problems] == [("tree-split-pointer", key)]

    changes[key] = with_line(changes[key], f"The rule: `{SPLIT_RULE_FILE}`.")
    changes[SPLIT_RULE_FILE] = (
        "---\nname: train_val_test\ndescription: The split rule.\n---\n"
    )
    assert problems_of(tmp_path, changes) == []


def test_split_wording_outside_the_pointer_folders_passes(tmp_path):
    text = with_line(RAG_MD, "Fine-tune with a test split.")
    assert problems_of(tmp_path, {"references/knowledge/rag.md": text}) == []


@pytest.mark.parametrize(
    "line",
    [
        "Call `GET /api/scores?split=test`.",
        'Send `{"split": "test"}`.',
        'Send {"split":"test"}.',
    ],
)
def test_test_split_request_fails(tmp_path, line):
    problems = problems_of(
        tmp_path, {"references/knowledge/rag.md": with_line(RAG_MD, line)}
    )
    assert rules_of(problems) == {("tree-test-split", "references/knowledge/rag.md")}


def test_test_split_request_in_help_articles_passes(tmp_path):
    text = with_line(EVALS_ARTICLE, "Use `split=test` for the final score.")
    assert problems_of(tmp_path, {"references/docs/evals.md": text}) == []


def test_test_split_reader_needs_the_pointer(tmp_path):
    reader = "references/knowledge/api_docs/get_api_projects.md"
    readers = (reader,)
    plain = with_line(RAG_MD, f"Read `{reader}`.")
    problems = problems_of(
        tmp_path, {"references/knowledge/rag.md": plain}, test_split_readers=readers
    )
    assert rules_of(problems) == {("tree-test-split", "references/knowledge/rag.md")}

    pointed = with_line(plain, f"Splits: `{SPLIT_RULE_FILE}`.")
    split_rule = with_line(
        "---\nname: train_val_test\ndescription: The split rule.\n---\n", f"`{reader}`"
    )
    changes = {"references/knowledge/rag.md": pointed, SPLIT_RULE_FILE: split_rule}
    assert problems_of(tmp_path, changes, test_split_readers=readers) == []


@pytest.mark.parametrize(
    "key, text, message",
    [
        (
            "SKILL.md",
            SKILL_MD.replace("name: kiln", "name: other"),
            "`name` must be `kiln`",
        ),
        (
            "SKILL.md",
            SKILL_MD.replace(
                "description: Work with Kiln.", "description: " + "x" * 1025
            ),
            "`description` must have 1 to 1024 characters",
        ),
        ("SKILL.md", "# Kiln\n" + SKILL_MD.split("---\n", 2)[2], "has no front matter"),
        ("SKILL.md", "---\nname: kiln\n", "front matter is not closed"),
        ("SKILL.md", "---\nname: [kiln\n---\n", "front matter is not valid YAML"),
        ("SKILL.md", "---\n- kiln\n---\n", "front matter is not a map"),
        (
            "references/client_guidance/chat/learn.md",
            LEARN_MD.replace("name: learn", "name: other"),
            "`name` must be the file stem, `learn`",
        ),
        (
            "references/knowledge/rag.md",
            RAG_MD.replace("---\n\n", "extra: 1\n---\n\n"),
            "front matter must have exactly `name` and `description`",
        ),
        (
            "references/knowledge/rag.md",
            RAG_MD.replace("description: RAG in Kiln.", "description: ''"),
            "`description` must be a text that is not empty",
        ),
        (
            "references/knowledge/api_docs/get_api_projects.md",
            "---\nname: x\n---\n# List\n",
            "must have no front matter",
        ),
        (
            "references/docs/evals.md",
            EVALS_ARTICLE.replace("/docs/evals", "/docs/other"),
            "`online_url` must be `https://docs.kiln.tech/docs/evals`",
        ),
        (
            "references/docs/README.md",
            DOCS_README.replace(
                "online_url: https://docs.kiln.tech/docs/\n", "title: Docs\n"
            ),
            "`online_url` must be `https://docs.kiln.tech/docs/`",
        ),
    ],
)
def test_front_matter_by_type(tmp_path, key, text, message):
    problems = [
        p for p in problems_of(tmp_path, {key: text}) if p.rule == "tree-front-matter"
    ]
    assert [p.path for p in problems] == [key]
    assert problems[0].message.startswith(message)


def test_front_matter_of_the_knowledge_trees_and_indexes(tmp_path):
    changes = {
        "references/levers/index.md": "# Levers\n\n`references/levers/prompt.md`\n",
        "references/levers/prompt.md": "---\ntitle: Prompt\n---\n",
        "references/improving_agents/index.md": "---\nname: index\n---\n\n`references/improving_agents/techniques/roll-up.md`\n",
        "references/improving_agents/techniques/roll-up.md": "---\ntitle: Roll up\n---\n\n`references/improving_agents/techniques/roll-up/example.md`\n",
        "references/improving_agents/techniques/roll-up/example.md": "---\ntitle: Example\n---\n",
        "references/docs/docs_index.md": "---\nonline_url: x\n---\n",
        "SKILL.md": with_line(
            SKILL_MD,
            "`references/levers/index.md` `references/improving_agents/index.md` `references/docs/docs_index.md`",
        ),
    }
    problems = [
        p for p in problems_of(tmp_path, changes) if p.rule == "tree-front-matter"
    ]
    assert sorted(p.path for p in problems) == [
        "references/docs/docs_index.md",
        "references/improving_agents/index.md",
        "references/improving_agents/techniques/roll-up/example.md",
    ]


def test_unreachable_file_fails(tmp_path):
    problems = problems_of(
        tmp_path,
        {
            "references/knowledge/orphan.md": "---\nname: orphan\ndescription: Orphan.\n---\n"
        },
    )
    assert problems == [
        Problem(
            "tree-unreachable",
            "references/knowledge/orphan.md",
            "not reached from SKILL.md",
        )
    ]


def test_a_tree_without_skill_md_reaches_nothing(tmp_path):
    problems = problems_of(tmp_path, {"SKILL.md": None})
    assert ("tree-unreachable", "SKILL.md") in rules_of(problems)
    assert ("tree-unreachable", "references/client_guidance/chat/learn.md") in rules_of(
        problems
    )


def test_many_unreachable_files_in_one_folder_are_one_line(tmp_path):
    orphans = {
        f"references/knowledge/api_docs/get_api_x{i:02}.md": "# X\n" for i in range(21)
    }
    problems = problems_of(tmp_path, orphans)
    assert problems == [
        Problem(
            "tree-unreachable",
            "references/knowledge/api_docs/",
            "21 files are not reached from SKILL.md, for example "
            + ", ".join(
                f"references/knowledge/api_docs/get_api_x{i:02}.md" for i in range(5)
            ),
        )
    ]


@pytest.mark.parametrize(
    "key, content, message",
    [
        ("references/knowledge/notes.txt", b"text", "is not a Markdown (.md) file"),
        (
            "references/knowledge/bad name.md",
            b"x",
            "name `bad name.md` has a character",
        ),
        ("references/knowledge/latin1.md", "caf\xe9".encode("latin-1"), "is not UTF-8"),
        ("references/knowledge/crlf.md", b"a\r\nb\n", "has a carriage return"),
    ],
)
def test_non_markdown_file_fails(tmp_path, key, content, message):
    root = write_tree(tmp_path / "skill", CLEAN_TREE)
    (root / key).write_bytes(content)
    file_problems = [p for p in check_tree(root) if p.rule == "tree-file"]
    assert [p.path for p in file_problems] == [key]
    assert file_problems[0].message.startswith(message)


def test_banned_terms_by_scope(tmp_path):
    changes = {
        "SKILL.md": with_line(
            SKILL_MD,
            "The Kiln Assistant is UI-only.\n`references/levers/index.md` `references/knowledge/kiln.md`",
        ),
        "references/knowledge/kiln.md": "---\nname: kiln\ndescription: x.\n---\n\nThe kiln assistant arm.\n",
        "references/levers/index.md": "# Levers\n\nEach arm calls get_task through the gateway.\n",
    }
    messages = {(p.path, p.message) for p in problems_of(tmp_path, changes)}
    assert messages == {
        ("SKILL.md", "line 12: banned term `UI-only`"),
        ("SKILL.md", "line 12: banned term `Kiln Assistant`"),
        ("references/levers/index.md", "line 3: banned term `get_task`"),
        ("references/levers/index.md", "line 3: banned term `gateway`"),
        ("references/levers/index.md", "line 3: banned term `arm`"),
    }


CHAT_WORDS_LINE = "Other MCP clients reach Kiln. An MCP client can."


@pytest.mark.parametrize(
    ("key", "text", "banned"),
    [
        ("references/knowledge/rag.md", RAG_MD, True),
        ("references/client_guidance/chat/learn.md", LEARN_MD, True),
        ("references/knowledge/api_docs/calling_the_kiln_api.md", "# Rules\n", True),
        ("references/knowledge/tools.md", RAG_MD.replace("rag", "tools"), False),
        ("references/docs/evals.md", EVALS_ARTICLE, False),
        ("references/knowledge/api_docs/get_api_projects.md", "# List\n", False),
    ],
)
def test_mcp_client_means_the_protocol_role_only(tmp_path, key, text, banned):
    changed = with_line(text, CHAT_WORDS_LINE)
    changes = {key: changed, "SKILL.md": with_line(SKILL_MD, f"`{key}`")}
    line = len(changed.splitlines())
    expected = [
        f"line {line}: banned term `MCP client`",
        f"line {line}: banned term `MCP clients`",
    ]
    messages = sorted(p.message for p in problems_of(tmp_path, changes))
    assert messages == (expected if banned else [])


@pytest.mark.parametrize(
    "text, banned",
    [
        ("Call `GET /api/model_info/models`.", False),
        ("Read `references/knowledge/api_docs/get_api_model_info_models.md`.", False),
        ("Use the model_info tool.", True),
        ("Use the Model_Info tool.", True),
        ("Use model_info_featured.", True),
        ("Read `references/client_guidance/chat/experiment_batch.md`.", True),
        ("This requires approval.", True),
    ],
)
def test_banned_terms_are_whole_tokens(tmp_path, text, banned):
    changes = {
        "references/knowledge/rag.md": with_line(RAG_MD, text),
        "references/client_guidance/chat/experiment_batch.md": "---\nname: experiment_batch\ndescription: x.\n---\n",
        "references/knowledge/api_docs/get_api_model_info_models.md": "# Models\n",
        "references/knowledge/api_docs/projects_api_list.md": CATALOGUE
        + "|`/api/model_info/models`|GET|M||get_api_model_info_models.md|\n",
        "SKILL.md": with_line(
            SKILL_MD, "`references/client_guidance/chat/experiment_batch.md`"
        ),
    }
    rag_problems = [
        p
        for p in problems_of(tmp_path, changes)
        if p.path == "references/knowledge/rag.md"
    ]
    assert bool(rag_problems) is banned
    assert all(p.rule == "tree-banned-term" for p in rag_problems)


def test_banned_terms_skip_the_api_docs(tmp_path):
    changes = {
        "references/knowledge/api_docs/get_api_projects.md": "# List\n\nThe model_info list; requires approval.\n"
    }
    assert problems_of(tmp_path, changes) == []


@pytest.mark.parametrize(
    "text, banned",
    [
        ("Build it with `references/knowledge/create_eval.md`.", False),
        ("Build it with `create_eval`.", True),
    ],
)
def test_a_file_named_like_an_operation_is_not_banned(tmp_path, text, banned):
    changes = {
        "references/knowledge/create_eval.md": "---\nname: create_eval\ndescription: x.\n---\n",
        "references/levers/index.md": f"# Levers\n\n{text}\n",
        "SKILL.md": with_line(SKILL_MD, "`references/levers/index.md`"),
    }
    found = [
        p
        for p in problems_of(tmp_path, changes)
        if p.path == "references/levers/index.md"
    ]
    assert bool(found) is banned
    assert all(p.rule == "tree-banned-term" for p in found)


def test_product_name_is_not_banned(tmp_path):
    changes = {
        "references/levers/index.md": "# Levers\n\nRun Kiln Harness Tuner, or the Kiln Harness Tuner CLI.\n",
        "SKILL.md": with_line(SKILL_MD, "`references/levers/index.md`"),
    }
    assert problems_of(tmp_path, changes) == []


def banned_in_levers_index(tmp_path, text: str) -> list[str]:
    changes = {
        "references/levers/index.md": f"# Levers\n\n{text}\n",
        "SKILL.md": with_line(SKILL_MD, "`references/levers/index.md`"),
    }
    return [
        p.message
        for p in problems_of(tmp_path, changes)
        if p.rule == "tree-banned-term"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Without `train_noise`, use a flip rate of 10%.",
        "Read `train_detectability`, `probe_results` and `lever_attempts`.",
        "Ask the user, or write it in `open_questions` or `rejected_summary`.",
        "The models are in `allowed_models` and `model_policy`.",
        "Kiln Harness Tuner installs it with `install_skill_bundle`.",
        "The record ends `— REJECTED AT VAL <MM-DD>`.",
    ],
)
def test_harness_tuner_inputs_and_outputs_are_allowed_in_the_knowledge(tmp_path, text):
    assert banned_in_levers_index(tmp_path, text) == []


@pytest.mark.parametrize(
    "text, term",
    [
        ("Then the planner plans it.", "the planner"),
        ("The planner's skill gives the order.", "the planner"),
        ("The builder writes it.", "the builder"),
        ("The analyzer reads it.", "the analyzer"),
        ("The tuner reads it.", "the tuner"),
    ],
)
def test_role_names_stay_banned_in_the_knowledge(tmp_path, text, term):
    assert banned_in_levers_index(tmp_path, text) == [f"line 3: banned term `{term}`"]


def test_harness_tuner_record_strings_may_hold_a_loop_word(tmp_path):
    record = "`- rejected at the val gate <MM-DD> vs baseline <rc> — `"
    assert banned_in_levers_index(tmp_path, f"A line {record}.") == []
    assert banned_in_levers_index(
        tmp_path, f"A line {record}, and the val gate rejects it."
    ) == ["line 3: banned term `val gate`"]


def test_every_rule_id_is_listed():
    assert len(TREE_RULES) == len(set(TREE_RULES)) == 11
