import ast
from pathlib import Path

from kiln_mcp_server import texts
from kiln_mcp_server.texts import (
    CALL_KILN_API_DESCRIPTION,
    PATH_DESCRIPTION,
    SERVER_INSTRUCTIONS,
    SKILL_TOOL_DESCRIPTION,
    WHAT_KILN_IS,
)


def test_what_kiln_is_is_the_shared_opening():
    assert (
        WHAT_KILN_IS
        == "Kiln is an app for building, evaluating and optimizing AI agents"
    )


def test_the_install_guide_stub_skill_opens_with_what_kiln_is():
    guide = Path(__file__).resolve().parents[3] / "agent_install.md"
    assert f"description: {WHAT_KILN_IS}." in guide.read_text(encoding="utf-8")


def test_server_instructions_start_with_what_kiln_is():
    assert SERVER_INSTRUCTIONS.startswith(WHAT_KILN_IS)


def test_skill_tool_description_holds_what_kiln_is_as_a_sentence():
    assert WHAT_KILN_IS + "." in SKILL_TOOL_DESCRIPTION


def test_server_instructions_fit_the_agent_limits():
    assert len(SERVER_INSTRUCTIONS) < 4000
    opening = SERVER_INSTRUCTIONS[:500]
    assert "kiln_skill" in opening
    assert "/kiln" in opening


def test_the_first_paragraph_of_the_instructions_stands_alone():
    assert SERVER_INSTRUCTIONS.index("\n\n") <= 500


# The skill's own words for its files: "skill file" and "endpoint doc".
WORDS_THE_SKILL_DOES_NOT_USE = ("reference file", "API reference")


def test_texts_use_the_skill_terms():
    texts = (
        SERVER_INSTRUCTIONS,
        SKILL_TOOL_DESCRIPTION,
        PATH_DESCRIPTION,
        CALL_KILN_API_DESCRIPTION,
    )
    for text in texts:
        for word in WORDS_THE_SKILL_DOES_NOT_USE:
            assert word not in text, word
    for text in (SERVER_INSTRUCTIONS, SKILL_TOOL_DESCRIPTION, PATH_DESCRIPTION):
        assert "skill file" in text
    for text in (SERVER_INSTRUCTIONS, CALL_KILN_API_DESCRIPTION):
        assert "endpoint doc" in text


def test_skill_tool_description_names_the_slash_command():
    assert "/kiln" in SKILL_TOOL_DESCRIPTION


def test_path_description_says_how_to_use_the_argument():
    assert PATH_DESCRIPTION.startswith("Optional.")
    assert "relative to the skill root" in PATH_DESCRIPTION


def test_call_kiln_api_description_sends_the_agent_to_the_skill_first():
    assert CALL_KILN_API_DESCRIPTION.startswith("Call the Kiln REST API.")
    for name in ("`kiln_skill`", "`body_limit`", "`save_to_tmpfile`", "`jq_filter`"):
        assert name in CALL_KILN_API_DESCRIPTION


def test_texts_module_imports_nothing():
    tree = ast.parse(Path(texts.__file__).read_text(encoding="utf-8"))
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert imports == []
