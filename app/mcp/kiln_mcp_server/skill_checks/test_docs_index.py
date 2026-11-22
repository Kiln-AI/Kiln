import pytest

from kiln_mcp_server.conftest import write_tree
from kiln_mcp_server.skill_checks.docs_index import (
    DOCS_INDEX_PATH,
    DOCS_INDEX_RULE,
    docs_index_problems,
    online_url_for,
    render_docs_index,
    write_docs_index,
)
from kiln_mcp_server.skill_checks.knowledge_schema import BUILD_COMMAND, Problem


@pytest.mark.parametrize(
    "path, url",
    [
        ("references/docs/evals.md", "https://docs.kiln.tech/docs/evals"),
        (
            "references/docs/guides/fine-tuning.md",
            "https://docs.kiln.tech/docs/guides/fine-tuning",
        ),
        ("references/docs/guides/README.md", "https://docs.kiln.tech/docs/guides"),
        ("references/docs/README.md", "https://docs.kiln.tech/docs/"),
    ],
)
def test_online_url_for(path, url):
    assert online_url_for(path) == url


@pytest.mark.parametrize(
    "path", ["references/knowledge/rag.md", "references/docs/image.png"]
)
def test_online_url_for_refuses_other_paths(path):
    with pytest.raises(ValueError, match="not a help article path"):
        online_url_for(path)


ARTICLES = {
    "references/docs/evals.md": (
        "---\ndescription: Measure  quality\n  with evals | judges.\n---\n\n"
        "```\n# not a heading\n```\n# Evals\n\nText.\n"
    ),
    "references/docs/guides/README.md": "# Guides | all\n",
    "references/docs/notes.md": "No heading.\n",
}

EXPECTED_INDEX = """\
# Kiln help articles

Copies of Kiln's public help pages. When you point the user at a page, give them the public URL.

| Article | Public URL | What it covers |
|---|---|---|
| [Evals](references/docs/evals.md) | https://docs.kiln.tech/docs/evals | Measure quality with evals \\| judges. |
| [Guides \\| all](references/docs/guides/README.md) | https://docs.kiln.tech/docs/guides |  |
| [notes](references/docs/notes.md) | https://docs.kiln.tech/docs/notes |  |
"""


def _skill(tmp_path, files):
    return write_tree(tmp_path / "skill", {"SKILL.md": "# Kiln\n", **files})


def test_render_docs_index(tmp_path):
    root = _skill(tmp_path, {**ARTICLES, DOCS_INDEX_PATH: "old\n"})
    assert render_docs_index(root) == EXPECTED_INDEX


def test_write_docs_index_writes_and_then_reports_no_change(tmp_path):
    root = _skill(tmp_path, ARTICLES)
    assert docs_index_problems(root) == [
        Problem(DOCS_INDEX_RULE, DOCS_INDEX_PATH, f"is missing; run `{BUILD_COMMAND}`")
    ]
    assert write_docs_index(root) == root / DOCS_INDEX_PATH
    assert (root / DOCS_INDEX_PATH).read_bytes() == EXPECTED_INDEX.encode("utf-8")
    assert docs_index_problems(root) == []
    assert write_docs_index(root) is None


def test_a_stale_docs_index_is_reported(tmp_path):
    root = _skill(tmp_path, {**ARTICLES, DOCS_INDEX_PATH: "old\n"})
    [problem] = docs_index_problems(root)
    assert problem.message.startswith("is stale")


def test_no_docs_index_without_help_articles(tmp_path):
    root = _skill(tmp_path, {"references/knowledge/rag.md": "x\n"})
    assert docs_index_problems(root) == []
    assert write_docs_index(root) is None
    assert not (root / DOCS_INDEX_PATH).exists()
