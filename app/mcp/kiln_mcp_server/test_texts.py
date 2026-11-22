import ast
from pathlib import Path

from kiln_mcp_server import texts
from kiln_mcp_server.texts import (
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


def test_server_instructions_start_with_what_kiln_is():
    assert SERVER_INSTRUCTIONS.startswith(WHAT_KILN_IS)


def test_skill_tool_description_holds_what_kiln_is_as_a_sentence():
    assert WHAT_KILN_IS + "." in SKILL_TOOL_DESCRIPTION


def test_server_instructions_fit_the_agent_limits():
    assert len(SERVER_INSTRUCTIONS) < 4000
    opening = SERVER_INSTRUCTIONS[:500]
    assert "kiln_skill" in opening
    assert "/kiln" in opening


def test_skill_tool_description_names_the_slash_command():
    assert "/kiln" in SKILL_TOOL_DESCRIPTION


def test_path_description_says_how_to_use_the_argument():
    assert PATH_DESCRIPTION.startswith("Optional.")
    assert "relative to the skill root" in PATH_DESCRIPTION


def test_texts_module_imports_nothing():
    tree = ast.parse(Path(texts.__file__).read_text(encoding="utf-8"))
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert imports == []
