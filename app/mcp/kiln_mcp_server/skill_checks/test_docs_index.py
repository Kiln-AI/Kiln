import pytest

from kiln_mcp_server.skill_checks.docs_index import online_url_for


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
