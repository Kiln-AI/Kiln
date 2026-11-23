import pytest
from provider_utils import (
    opencode_availability,
    opencode_name_key,
    parse_opencode_deprecations,
)

DOCS_HTML = """
<h3 id="free-models">Free models</h3>
<table><tbody><tr><td>Big Pickle</td><td>Free</td></tr></tbody></table>
<h3 id="deprecated-models"><button>Deprecated models</button></h3>
<div class="docs-table-scroll"><table><thead><tr><th>Model</th><th>Deprecation date</th></tr></thead>
<tbody><tr><td>GLM 5.2</td><td>November 19, 2026</td></tr><tr><td>GPT 5.2 Codex</td><td>July 23, 2026</td></tr><tr><td>Claude Haiku 3.5</td><td>February 16, 2026</td></tr></tbody></table></div>
<h3 id="privacy">Privacy</h3>
"""


def test_opencode_name_key_ignores_case_spaces_and_hyphens():
    assert opencode_name_key("GPT 5.2 Codex") == "gpt5.2codex"
    assert opencode_name_key("GPT-5.2 Codex") == "gpt5.2codex"
    assert opencode_name_key("gpt-5.2-codex") == "gpt5.2codex"


def test_parse_opencode_deprecations_reads_only_the_deprecated_table():
    assert parse_opencode_deprecations(DOCS_HTML) == {
        "glm5.2": "2026-11-19",
        "gpt5.2codex": "2026-07-23",
        "claudehaiku3.5": "2026-02-16",
    }


def test_parse_opencode_deprecations_raises_without_the_table():
    with pytest.raises(RuntimeError):
        parse_opencode_deprecations("<h3 id='privacy'>Privacy</h3>")


def test_opencode_availability_matches_by_name_then_id():
    models = [
        {"id": "glm-5.2", "name": "GLM-5.2"},
        {"id": "claude-3-5-haiku", "name": "Claude Haiku 3.5"},
        {"id": "gpt-5.2-codex", "name": "Codex 5.2"},
        {"id": "glm-5.3", "name": "GLM-5.3"},
    ]
    ids, dates = opencode_availability(models, parse_opencode_deprecations(DOCS_HTML))
    assert ids == {"glm-5.2", "claude-3-5-haiku", "gpt-5.2-codex", "glm-5.3"}
    assert dates == {
        "glm-5.2": "2026-11-19",
        "claude-3-5-haiku": "2026-02-16",
        "gpt-5.2-codex": "2026-07-23",
    }
