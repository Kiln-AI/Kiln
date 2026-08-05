"""Tests for CodeTool datamodel — validation, defaults, save/load, parent registration."""

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.project import Project

VALID_SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "string"}},
}
EMPTY_SCHEMA = {"type": "object", "properties": {}}

SYNC_RUN = "def run(x):\n    return x\n"
ASYNC_RUN = "async def run(x):\n    return x\n"


def _make_code_tool(**overrides):
    defaults = {
        "name": "My Tool",
        "tool_function_name": "my_tool",
        "tool_description": "Does things",
        "parameters_schema": VALID_SCHEMA,
        "code": SYNC_RUN,
    }
    defaults.update(overrides)
    return CodeTool(**defaults)


# ---------------------------------------------------------------------------
# Code validation trio
# ---------------------------------------------------------------------------


class TestCodeValidation:
    def test_valid_sync_run(self):
        ct = _make_code_tool(code=SYNC_RUN)
        assert ct.code == SYNC_RUN

    def test_valid_async_run(self):
        ct = _make_code_tool(code=ASYNC_RUN)
        assert ct.code == ASYNC_RUN

    def test_missing_run_rejected(self):
        with pytest.raises(ValidationError, match="module-level 'run' function"):
            _make_code_tool(code="def helper():\n    pass\n")

    def test_nested_run_rejected(self):
        code = "class Foo:\n    def run(self):\n        pass\n"
        with pytest.raises(ValidationError, match="module-level 'run' function"):
            _make_code_tool(code=code)

    def test_run_as_variable_rejected(self):
        with pytest.raises(ValidationError, match="module-level 'run' function"):
            _make_code_tool(code="run = 42\n")

    def test_syntax_error_rejected(self):
        with pytest.raises(ValidationError, match="syntax error"):
            _make_code_tool(code="def run(\n")

    def test_code_size_cap(self):
        big_code = "def run():\n    pass\n" + "# " + "x" * (64 * 1024)
        with pytest.raises(ValidationError, match="too large"):
            _make_code_tool(code=big_code)

    def test_empty_code_rejected(self):
        with pytest.raises(ValidationError, match="module-level 'run' function"):
            _make_code_tool(code="")


# ---------------------------------------------------------------------------
# Function name validation
# ---------------------------------------------------------------------------


class TestFunctionName:
    @pytest.mark.parametrize(
        "name",
        ["a", "my_tool", "tool123", "a" * 64],
    )
    def test_valid_names(self, name):
        ct = _make_code_tool(tool_function_name=name)
        assert ct.tool_function_name == name

    @pytest.mark.parametrize(
        "name",
        [
            "MyTool",  # uppercase
            "1tool",  # starts with digit
            "_tool",  # starts with underscore
            "tool-name",  # hyphen
            "a" * 65,  # too long
            "",  # empty
            "my_tool\n",  # trailing newline
        ],
    )
    def test_invalid_names(self, name):
        with pytest.raises(ValidationError, match="tool_function_name"):
            _make_code_tool(tool_function_name=name)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_valid_schema(self):
        ct = _make_code_tool(parameters_schema=VALID_SCHEMA)
        assert ct.parameters_schema == VALID_SCHEMA

    def test_empty_properties_allowed(self):
        ct = _make_code_tool(parameters_schema=EMPTY_SCHEMA)
        assert ct.parameters_schema == EMPTY_SCHEMA

    def test_non_object_schema_rejected(self):
        with pytest.raises(ValidationError, match="object with properties"):
            _make_code_tool(parameters_schema={"type": "string"})

    def test_missing_properties_rejected(self):
        with pytest.raises(ValidationError, match="object with properties"):
            _make_code_tool(parameters_schema={"type": "object"})


# ---------------------------------------------------------------------------
# Allowlist validation
# ---------------------------------------------------------------------------


class TestAllowlistValidation:
    def test_valid_allowlist(self):
        ct = _make_code_tool(
            tool_allowlist=[
                "kiln_tool::add_numbers",
                "mcp::remote::server1::tool1",
            ]
        )
        assert len(ct.tool_allowlist) == 2

    def test_empty_allowlist(self):
        ct = _make_code_tool(tool_allowlist=[])
        assert ct.tool_allowlist == []

    def test_rejects_skill_ids(self):
        with pytest.raises(ValidationError, match="Skill tool IDs cannot"):
            _make_code_tool(tool_allowlist=["kiln_tool::skill::some_skill"])

    def test_rejects_unmanaged_ids(self):
        with pytest.raises(ValidationError, match="Unmanaged tool IDs cannot"):
            _make_code_tool(tool_allowlist=["kiln_unmanaged::some_tool"])

    def test_rejects_duplicates(self):
        with pytest.raises(ValidationError, match="Duplicate tool ID"):
            _make_code_tool(
                tool_allowlist=[
                    "kiln_tool::add_numbers",
                    "kiln_tool::add_numbers",
                ]
            )

    def test_rejects_self_reference(self):
        ct_id = "123456789012"
        with pytest.raises(ValidationError, match="cannot reference itself"):
            _make_code_tool(
                id=ct_id,
                tool_allowlist=[f"kiln_tool::code::{ct_id}"],
            )

    def test_rejects_invalid_tool_id(self):
        with pytest.raises(ValidationError, match="Invalid tool ID"):
            _make_code_tool(tool_allowlist=["not_a_valid_tool_id"])


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_timeout(self):
        ct = _make_code_tool()
        assert ct.timeout_seconds == 60

    def test_default_allowlist(self):
        ct = _make_code_tool()
        assert ct.tool_allowlist == []

    def test_default_archived(self):
        ct = _make_code_tool()
        assert ct.is_archived is False

    def test_default_description(self):
        ct = _make_code_tool()
        assert ct.description is None

    def test_timeout_min_1(self):
        ct = _make_code_tool(timeout_seconds=1)
        assert ct.timeout_seconds == 1

    def test_timeout_below_min_rejected(self):
        with pytest.raises(ValidationError):
            _make_code_tool(timeout_seconds=0)

    def test_tool_description_required(self):
        with pytest.raises(ValidationError):
            _make_code_tool(tool_description="")


# ---------------------------------------------------------------------------
# Save/load round-trip and parent registration
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        project = Project(name="test_project", path=tmp_path / "project")
        project.save_to_file()

        ct = _make_code_tool(
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        ct.parent = project
        ct.save_to_file()

        loaded = CodeTool.from_id_and_parent_path(ct.id, project.path)
        assert loaded is not None
        assert loaded.tool_function_name == ct.tool_function_name
        assert loaded.code == ct.code
        assert loaded.parameters_schema == ct.parameters_schema
        assert loaded.tool_description == ct.tool_description
        assert loaded.timeout_seconds == ct.timeout_seconds
        assert loaded.tool_allowlist == ct.tool_allowlist

    def test_project_code_tools_accessor(self, tmp_path):
        project = Project(name="test_project", path=tmp_path / "project")
        project.save_to_file()

        ct = _make_code_tool()
        ct.parent = project
        ct.save_to_file()

        tools = project.code_tools()
        assert len(tools) == 1
        assert tools[0].tool_function_name == "my_tool"
