import json
import threading
from pathlib import Path

import pytest

from kiln_ai.datamodel import Memory, Project, Task
from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.memory import MAX_CONTENT_LENGTH, MAX_OVERVIEW_LENGTH
from kiln_ai.datamodel.tool_id import (
    build_memory_tool_id,
    memory_operation_from_tool_id,
)
from kiln_ai.memory import MemoryListResult, MemoryStore, MemorySummary
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


def _descriptions(node) -> list[str]:
    if isinstance(node, dict):
        found = (
            [node["description"]] if isinstance(node.get("description"), str) else []
        )
        return found + [d for value in node.values() for d in _descriptions(value)]
    if isinstance(node, list):
        return [d for value in node for d in _descriptions(value)]
    return []


@pytest.mark.parametrize(
    "operation", ["save", "list", "get", "update", "delete", "summary"]
)
async def test_descriptions_do_not_invite_null(project, operation):
    # The adapter checks arguments against the schema before run(), and the
    # schemas do not allow null, so a null the model was told to send ends the run.
    definition = await tool(project, operation).toolcall_definition()
    for text in _descriptions(definition["function"]):
        assert "null" not in text.lower(), text


@pytest.mark.parametrize(
    "operation, args, valid",
    [
        ("save", {"overview": "o", "scope": "project"}, True),
        ("save", {"overview": "o", "scope": "project", "content": None}, False),
        ("update", {"id": "1", "content": ""}, True),
        ("update", {"id": "1", "tags": None}, False),
    ],
)
async def test_schema_check_the_adapter_runs(project, operation, args, valid):
    definition = await tool(project, operation).toolcall_definition()
    schema = json.dumps(definition["function"]["parameters"])
    if valid:
        validate_schema_with_value_error(args, schema)
    else:
        with pytest.raises(ValueError):
            validate_schema_with_value_error(args, schema)


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


@pytest.mark.parametrize("field", ["overview", "content", "tags", "scope"])
async def test_update_null_field_is_not_provided(project, field):
    # A model can send an explicit null. That must leave the field as it is,
    # not clear it (and not fail on a required field).
    saved = out(
        await tool(project, "save").run(
            overview="orig", scope="project", content="body", tags=["t"]
        )
    )
    result = await tool(project, "update").run(id=saved["id"], **{field: None})
    assert not result.is_error
    memory = out(result)["memory"]
    assert memory["overview"] == "orig"
    assert memory["content"] == "body"
    assert memory["tags"] == ["t"]
    assert memory["scope"] == "project"


# --- the store runs off the event loop ---


@pytest.mark.parametrize(
    "operation,store_method,kwargs",
    [
        ("save", "save_memory", {"overview": "a", "scope": "project"}),
        ("list", "list_memories", {}),
        ("get", "get_memories", {"ids": ["999999999999"]}),
        ("update", "update_memory", {"id": "999999999999", "overview": "x"}),
        ("delete", "delete_memory", {"id": "999999999999"}),
        ("summary", "memory_summary", {}),
    ],
)
async def test_store_call_runs_in_a_worker_thread(
    project, monkeypatch, operation, store_method, kwargs
):
    # The store does blocking disk scans and regex work. The tools are async, so
    # each store call must run in a worker thread, not on the event loop thread.
    loop_thread = threading.get_ident()
    call_threads: list[int] = []
    original = getattr(MemoryStore, store_method)

    def recording(self, *args, **kw):
        call_threads.append(threading.get_ident())
        return original(self, *args, **kw)

    monkeypatch.setattr(MemoryStore, store_method, recording)
    await tool(project, operation).run(**kwargs)

    assert len(call_threads) == 1
    assert call_threads[0] != loop_thread


# --- every schema property reaches the store ---


_SAVED = Memory(overview="o", scope="project")
_FORWARDING_CASES = [
    (
        "save",
        "save_memory",
        _SAVED,
        {"overview": "o", "scope": "task::1", "content": "c", "tags": ["t"]},
        (),
        {"overview": "o", "scope": "task::1", "content": "c", "tags": ["t"]},
    ),
    (
        "list",
        "list_memories",
        MemoryListResult(listings=[], matched=0, remaining=0, remaining_tag_counts={}),
        {
            "scope": "task::1",
            "tags": ["t"],
            "content_match": "x",
            "limit": 3,
            "offset": 2,
        },
        (),
        {
            "scope": "task::1",
            "tags": ["t"],
            "content_match": "x",
            "limit": 3,
            "offset": 2,
        },
    ),
    ("get", "get_memories", [], {"ids": ["1", "2"]}, (["1", "2"],), {}),
    (
        "update",
        "update_memory",
        _SAVED,
        {"id": "1", "overview": "o", "content": "c", "tags": ["t"], "scope": "s"},
        ("1",),
        {"overview": "o", "content": "c", "tags": ["t"], "scope": "s"},
    ),
    ("delete", "delete_memory", None, {"id": "1"}, ("1",), {}),
    (
        "summary",
        "memory_summary",
        MemorySummary(total=0, scopes=[]),
        {"scope": "task::1"},
        (),
        {"scope": "task::1"},
    ),
]


@pytest.mark.parametrize(
    "operation, store_method, returns, tool_args, want_args, want_kwargs",
    _FORWARDING_CASES,
)
async def test_tool_forwards_every_parameter_to_the_store(
    project,
    monkeypatch,
    operation,
    store_method,
    returns,
    tool_args,
    want_args,
    want_kwargs,
):
    definition = await tool(project, operation).toolcall_definition()
    assert set(tool_args) == set(definition["function"]["parameters"]["properties"])
    calls: list[tuple[tuple, dict]] = []

    def recording(self, *args, **kwargs):
        calls.append((args, kwargs))
        return returns

    monkeypatch.setattr(MemoryStore, store_method, recording)
    result = await tool(project, operation).run(**tool_args)

    assert not result.is_error, result.output
    assert calls == [(want_args, want_kwargs)]


# --- error mapping (store errors become tool errors, not exceptions) ---


async def test_save_over_length_overview_is_tool_error(project):
    result = await tool(project, "save").run(
        overview="a" * (MAX_OVERVIEW_LENGTH + 1), scope="project"
    )
    assert result.is_error
    assert result.error_message


@pytest.mark.parametrize("kwargs", [{"scope": "project"}, {"overview": "a"}, {}])
async def test_save_missing_required_param_is_tool_error(project, kwargs):
    # An LLM can omit a "required" param; that must be a tool error, not a crash.
    result = await tool(project, "save").run(**kwargs)
    assert result.is_error
    assert result.error_message


async def test_list_negative_pagination_is_tool_error(project):
    result = await tool(project, "list").run(limit=-1)
    assert result.is_error


async def test_list_accepts_whole_number_floats_for_paging(project):
    # The adapter's schema check lets 2.0 through as an integer, and some
    # providers send every number as a float.
    for i in range(3):
        await tool(project, "save").run(overview=f"m{i}", scope="project")
    definition = await tool(project, "list").toolcall_definition()
    args = {"limit": 2.0, "offset": 1.0}
    validate_schema_with_value_error(
        args, json.dumps(definition["function"]["parameters"])
    )

    result = await tool(project, "list").run(**args)
    assert not result.is_error
    assert [m["overview"] for m in out(result)["memories"]] == ["m1", "m0"]


@pytest.mark.parametrize("args", [{"limit": 2.5}, {"offset": "1"}, {"limit": True}])
async def test_list_non_whole_number_paging_is_tool_error(project, args):
    result = await tool(project, "list").run(**args)
    assert result.is_error


async def test_list_invalid_regex_is_tool_error(project):
    result = await tool(project, "list").run(content_match="[unclosed")
    assert result.is_error


async def test_list_catastrophic_regex_is_tool_error(project):
    # Nested quantifiers backtrack for an exponential time on this content.
    Memory(
        parent=project,
        overview="slow note.",
        scope="project",
        content="a" * (MAX_CONTENT_LENGTH - 1) + "!",
    ).save_to_file()
    result = await tool(project, "list").run(content_match=r"(\w+\s?)+$")
    assert result.is_error
    assert "too expensive" in result.output


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


async def test_get_skips_an_unreadable_memory(project):
    good = out(await tool(project, "save").run(overview="good", scope="project"))
    bad = out(await tool(project, "save").run(overview="bad", scope="project"))
    bad_path = project.path.parent / "assistant_memory" / bad["id"] / "memory.kiln"
    bad_path.write_text("{ not json", encoding="utf-8")

    result = await tool(project, "get").run(ids=[good["id"], bad["id"]])
    assert not result.is_error
    assert [m["id"] for m in out(result)["memories"]] == [good["id"]]


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


@pytest.mark.parametrize(
    "operation, store_method, kwargs",
    [
        ("get", "get_memories", {"ids": ["1"]}),
        ("summary", "memory_summary", {}),
    ],
)
@pytest.mark.parametrize("error", [ValueError("bad"), FileNotFoundError("gone")])
async def test_read_tool_store_failure_is_tool_error(
    project, monkeypatch, operation, store_method, kwargs, error
):
    def failing(self, *args, **kw):
        raise error

    monkeypatch.setattr(MemoryStore, store_method, failing)
    result = await tool(project, operation).run(**kwargs)
    assert result.is_error
    assert result.error_message == str(error)


@pytest.mark.parametrize(
    "operation, store_method, kwargs",
    [
        ("save", "save_memory", {"overview": "o", "scope": "project"}),
        ("list", "list_memories", {}),
        ("update", "update_memory", {"id": "1", "overview": "o"}),
        ("delete", "delete_memory", {"id": "1"}),
    ],
)
async def test_store_filesystem_failure_is_tool_error(
    project, monkeypatch, operation, store_method, kwargs
):
    # A filesystem failure (permissions, full disk) must come back as a tool error,
    # not escape run() and fail the agent's whole turn.
    error = PermissionError("denied")

    def failing(self, *args, **kw):
        raise error

    monkeypatch.setattr(MemoryStore, store_method, failing)
    result = await tool(project, operation).run(**kwargs)
    assert result.is_error
    assert result.error_message == str(error)
