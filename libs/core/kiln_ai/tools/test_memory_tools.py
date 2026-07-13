import json
from pathlib import Path

import pytest

from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.tool_id import (
    build_memory_tool_id,
    memory_operation_from_tool_id,
)
from kiln_ai.tools.memory_tools import memory_tool_from_id
from kiln_ai.tools.tool_registry import tool_from_id


@pytest.fixture
def project(tmp_path: Path) -> Project:
    project = Project(name="tools_test", path=tmp_path / "project.kiln")
    project.save_to_file()
    return project


@pytest.fixture
def task(project: Project) -> Task:
    return Task(name="a_task", instruction="do a thing", parent=project)


def tool(project: Project, operation: str):
    return memory_tool_from_id(build_memory_tool_id(operation), project)


def out(result):
    return json.loads(result.output)


# --- tool_id scheme ---


@pytest.mark.parametrize(
    "operation", ["save", "list", "get", "update", "delete", "summary"]
)
def test_build_and_parse_tool_id(operation):
    tool_id = build_memory_tool_id(operation)
    assert tool_id == f"kiln_tool::memory::{operation}"
    assert memory_operation_from_tool_id(tool_id) == operation


@pytest.mark.parametrize(
    "bad", ["kiln_tool::memory::nope", "kiln_tool::memory::", "kiln_tool::memory"]
)
def test_parse_tool_id_invalid(bad):
    with pytest.raises(ValueError):
        memory_operation_from_tool_id(bad)


def test_build_tool_id_unknown_operation():
    with pytest.raises(ValueError):
        build_memory_tool_id("frobnicate")


# --- toolcall definitions ---


@pytest.mark.parametrize(
    "operation,name,required",
    [
        ("save", "save_memory", ["overview", "scope"]),
        ("list", "list_memories", []),
        ("get", "get_memories", ["ids"]),
        ("update", "update_memory", ["id"]),
        ("delete", "delete_memory", ["id"]),
        ("summary", "memory_summary", []),
    ],
)
async def test_toolcall_definition(project, operation, name, required):
    definition = await tool(project, operation).toolcall_definition()
    assert definition["function"]["name"] == name
    assert definition["function"]["parameters"]["required"] == required
    # scope is an explicit param on every write tool (no injection).
    if operation in ("save", "update"):
        assert "scope" in definition["function"]["parameters"]["properties"]


# --- run round-trip ---


async def test_save_and_get_round_trip(project):
    save_result = await tool(project, "save").run(
        overview="API X limited to 5rps", scope="project", tags=["api_quirk"]
    )
    saved = out(save_result)
    assert not save_result.is_error
    memory_id = saved["id"]
    assert saved["memory"]["overview"] == "API X limited to 5rps"

    got = out(await tool(project, "get").run(ids=[memory_id]))
    assert got["memories"][0]["overview"] == "API X limited to 5rps"


async def test_list_and_summary(project):
    await tool(project, "save").run(overview="a", scope="project", tags=["x"])
    await tool(project, "save").run(overview="b", scope="task::1")

    listed = out(await tool(project, "list").run())
    assert listed["matched"] == 2

    listed_scoped = out(await tool(project, "list").run(scope="task::1"))
    assert listed_scoped["matched"] == 1
    assert listed_scoped["memories"][0]["content_length"] == 0

    summary = out(await tool(project, "summary").run())
    assert summary["total"] == 2
    assert {s["scope"] for s in summary["scopes"]} == {"project", "task::1"}


async def test_list_truncation_note(project):
    for i in range(5):
        await tool(project, "save").run(
            overview=f"m{i}", scope="project", tags=["probe"]
        )
    listed = out(await tool(project, "list").run(limit=2))
    assert listed["matched"] == 5
    assert "3 more" in listed["note"]
    assert "probe(3)" in listed["note"]


async def test_update_partial_and_delete(project):
    saved = out(
        await tool(project, "save").run(
            overview="orig", scope="project", content="c", tags=["t"]
        )
    )
    memory_id = saved["id"]

    updated = out(await tool(project, "update").run(id=memory_id, overview="changed"))
    assert updated["memory"]["overview"] == "changed"
    assert updated["memory"]["content"] == "c"  # untouched

    deleted = out(await tool(project, "delete").run(id=memory_id))
    assert deleted["deleted"] == memory_id
    assert out(await tool(project, "list").run())["matched"] == 0


async def test_update_clears_content_with_empty_string(project):
    saved = out(
        await tool(project, "save").run(
            overview="orig", scope="project", content="something"
        )
    )
    updated = out(await tool(project, "update").run(id=saved["id"], content=""))
    assert updated["memory"]["content"] is None


# --- error mapping (store errors become tool errors, not exceptions) ---


async def test_save_over_length_overview_is_tool_error(project):
    result = await tool(project, "save").run(overview="a" * 141, scope="project")
    assert result.is_error
    assert result.error_message


async def test_list_invalid_regex_is_tool_error(project):
    result = await tool(project, "list").run(content_match="[unclosed")
    assert result.is_error


async def test_update_unknown_id_is_tool_error(project):
    result = await tool(project, "update").run(id="999999999999", overview="x")
    assert result.is_error


async def test_delete_unknown_id_is_tool_error(project):
    result = await tool(project, "delete").run(id="999999999999")
    assert result.is_error


async def test_get_unknown_ids_omitted(project):
    saved = out(await tool(project, "save").run(overview="a", scope="project"))
    got = out(await tool(project, "get").run(ids=[saved["id"], "999999999999"]))
    assert len(got["memories"]) == 1


# --- registry integration ---


_OPERATION_TOOL_NAMES = {
    "save": "save_memory",
    "list": "list_memories",
    "get": "get_memories",
    "update": "update_memory",
    "delete": "delete_memory",
    "summary": "memory_summary",
}


@pytest.mark.parametrize("operation", list(_OPERATION_TOOL_NAMES))
async def test_tool_from_id_resolves_bound_to_project(task, operation):
    resolved = tool_from_id(build_memory_tool_id(operation), task)
    definition = await resolved.toolcall_definition()
    assert definition["function"]["name"] == _OPERATION_TOOL_NAMES[operation]
    # Bound to the task's project store: a save is visible via the project.
    if operation == "save":
        result = await resolved.run(overview="via registry", scope="project")
        assert not result.is_error
        project = task.parent_project()
        assert any(m.overview == "via registry" for m in project.memories())


def test_tool_from_id_without_project_raises():
    with pytest.raises(ValueError):
        tool_from_id(build_memory_tool_id("list"), None)
