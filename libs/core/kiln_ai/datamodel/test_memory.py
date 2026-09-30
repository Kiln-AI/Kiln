import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel import Memory, Project


@pytest.fixture
def project(tmp_path: Path) -> Project:
    project = Project(name="memory_test", path=tmp_path / "project.kiln")
    project.save_to_file()
    return project


def make_memory(**overrides) -> Memory:
    data = {"overview": "an overview", "scope": "project"}
    data.update(overrides)
    return Memory(**data)


# --- overview ---


def test_overview_accepts_max_length():
    m = make_memory(overview="a" * 140)
    assert len(m.overview) == 140


def test_overview_rejects_over_length():
    with pytest.raises(ValidationError):
        make_memory(overview="a" * 141)


def test_overview_rejects_over_length_only_after_strip():
    # 140 real chars plus surrounding whitespace should be accepted (stripped first).
    m = make_memory(overview="  " + "a" * 140 + "  ")
    assert m.overview == "a" * 140


@pytest.mark.parametrize("bad", ["line1\nline2", "line1\r\nline2", "a\rb"])
def test_overview_rejects_interior_newlines(bad):
    with pytest.raises(ValidationError):
        make_memory(overview=bad)


def test_overview_trailing_newline_is_stripped():
    # A trailing newline is just trailing whitespace: normalized away, not rejected.
    assert make_memory(overview="trailing\n").overview == "trailing"


@pytest.mark.parametrize("empty", ["", "   ", "\t"])
def test_overview_rejects_empty(empty):
    with pytest.raises(ValidationError):
        make_memory(overview=empty)


def test_overview_strips():
    assert make_memory(overview="  hello  ").overview == "hello"


# --- content ---


def test_content_defaults_none():
    assert make_memory().content is None


def test_content_accepts_max_length():
    m = make_memory(content="a" * 2000)
    assert len(m.content) == 2000


def test_content_rejects_over_length():
    with pytest.raises(ValidationError):
        make_memory(content="a" * 2001)


@pytest.mark.parametrize("empty", ["", "   ", "\n"])
def test_content_empty_becomes_none(empty):
    assert make_memory(content=empty).content is None


def test_content_allows_newlines():
    m = make_memory(content="line1\nline2")
    assert m.content == "line1\nline2"


def test_content_strips():
    assert make_memory(content="  body  ").content == "body"


# --- tags ---


def test_tags_default_empty():
    assert make_memory().tags == []


def test_tags_reject_space():
    with pytest.raises(ValidationError):
        make_memory(tags=["has space"])


def test_tags_reject_empty_string():
    with pytest.raises(ValidationError):
        make_memory(tags=[""])


def test_tags_accept_snake_case():
    m = make_memory(tags=["api_quirk", "dead_end"])
    assert m.tags == ["api_quirk", "dead_end"]


# --- scope ---


def test_scope_required():
    with pytest.raises(ValidationError):
        Memory(overview="an overview")


def test_scope_accepts_max_length():
    m = make_memory(scope="s" * 255)
    assert len(m.scope) == 255


def test_scope_rejects_over_length():
    with pytest.raises(ValidationError):
        make_memory(scope="s" * 256)


@pytest.mark.parametrize("bad", ["a\nb", "a\r\nb"])
def test_scope_rejects_newlines(bad):
    with pytest.raises(ValidationError):
        make_memory(scope=bad)


@pytest.mark.parametrize("empty", ["", "   "])
def test_scope_rejects_empty(empty):
    with pytest.raises(ValidationError):
        make_memory(scope=empty)


def test_scope_strips():
    assert make_memory(scope="  project  ").scope == "project"


@pytest.mark.parametrize(
    "scope",
    ["project", "task::184623901234", "task::deleted_task_id", "anything_opaque"],
)
def test_scope_accepts_opaque_and_dangling(scope):
    # No validation beyond format: any opaque string, including a dangling task id.
    assert make_memory(scope=scope).scope == scope


# --- persistence / registration ---


def test_saved_under_project_id_only_folder(project: Project):
    memory = Memory(parent=project, overview="an overview", scope="project")
    memory.save_to_file()

    assert project.path is not None
    expected = project.path.parent / "assistant_memory" / str(memory.id) / "memory.kiln"
    assert memory.path == expected
    # id-only subfolder: no name prefix in the folder name.
    assert memory.path.parent.name == memory.id


def test_project_memories_accessor(project: Project):
    Memory(parent=project, overview="one", scope="project").save_to_file()
    Memory(parent=project, overview="two", scope="task::1", tags=["x"]).save_to_file()

    memories = project.memories()
    assert {m.overview for m in memories} == {"one", "two"}


def test_project_no_memory_folder_returns_empty(project: Project):
    assert project.memories() == []


def test_roundtrip_save_load_equal(project: Project):
    memory = Memory(
        parent=project,
        overview="round trip",
        scope="task::9",
        content="body text",
        tags=["probe", "dead_end"],
    )
    memory.save_to_file()

    loaded = Memory.load_from_file(memory.path)
    assert loaded.overview == "round trip"
    assert loaded.content == "body text"
    assert loaded.tags == ["probe", "dead_end"]
    assert loaded.scope == "task::9"
    assert loaded.id == memory.id


def test_load_leniency_boundary_values(project: Project):
    # Max-length values that once saved must always load without error.
    memory = Memory(
        parent=project,
        overview="o" * 140,
        scope="s" * 255,
        content="c" * 2000,
    )
    memory.save_to_file()

    loaded = Memory.load_from_file(memory.path)
    assert len(loaded.overview) == 140
    assert len(loaded.scope) == 255
    assert len(loaded.content) == 2000


def test_on_disk_shape(project: Project):
    memory = Memory(parent=project, overview="disk", scope="project")
    memory.save_to_file()

    raw = json.loads(memory.path.read_text())
    assert raw["model_type"] == "memory"
    assert raw["overview"] == "disk"
    assert raw["scope"] == "project"
    assert raw["content"] is None
