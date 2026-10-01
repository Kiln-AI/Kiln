import json
import os
import stat
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel import Memory, Project
from kiln_ai.datamodel import memory as memory_module
from kiln_ai.datamodel.memory import (
    MAX_CONTENT_LENGTH,
    MAX_OVERVIEW_LENGTH,
    MAX_SCOPE_LENGTH,
)


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
    m = make_memory(overview="a" * MAX_OVERVIEW_LENGTH)
    assert len(m.overview) == MAX_OVERVIEW_LENGTH


def test_overview_rejects_over_length():
    with pytest.raises(ValidationError):
        make_memory(overview="a" * (MAX_OVERVIEW_LENGTH + 1))


def test_overview_rejects_over_length_only_after_strip():
    # Max-length real chars plus surrounding whitespace: accepted (stripped first).
    m = make_memory(overview="  " + "a" * MAX_OVERVIEW_LENGTH + "  ")
    assert m.overview == "a" * MAX_OVERVIEW_LENGTH


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
    m = make_memory(content="a" * MAX_CONTENT_LENGTH)
    assert len(m.content) == MAX_CONTENT_LENGTH


def test_content_rejects_over_length():
    with pytest.raises(ValidationError):
        make_memory(content="a" * (MAX_CONTENT_LENGTH + 1))


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
    m = make_memory(scope="s" * MAX_SCOPE_LENGTH)
    assert len(m.scope) == MAX_SCOPE_LENGTH


def test_scope_rejects_over_length():
    with pytest.raises(ValidationError):
        make_memory(scope="s" * (MAX_SCOPE_LENGTH + 1))


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
        overview="o" * MAX_OVERVIEW_LENGTH,
        scope="s" * MAX_SCOPE_LENGTH,
        content="c" * MAX_CONTENT_LENGTH,
    )
    memory.save_to_file()

    loaded = Memory.load_from_file(memory.path)
    assert len(loaded.overview) == MAX_OVERVIEW_LENGTH
    assert len(loaded.scope) == MAX_SCOPE_LENGTH
    assert len(loaded.content) == MAX_CONTENT_LENGTH


def test_on_disk_shape(project: Project):
    memory = Memory(parent=project, overview="disk", scope="project")
    memory.save_to_file()

    raw = json.loads(memory.path.read_text())
    assert raw["model_type"] == "memory"
    assert raw["overview"] == "disk"
    assert raw["scope"] == "project"
    assert raw["content"] is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
@pytest.mark.parametrize("umask", [0o022, 0o027, 0o002])
def test_saved_file_mode_matches_a_normal_write(tmp_path: Path, umask: int):
    # The atomic write must not leave the file with the 0o600 mode of a
    # tempfile.mkstemp file. It must match a .kiln file that core writes in place.
    old_umask = os.umask(umask)
    try:
        project = Project(name="mode_test", path=tmp_path / "project.kiln")
        project.save_to_file()  # core save_to_file: open(path, "w")
        memory = Memory(parent=project, overview="mode", scope="project")
        memory.save_to_file()
        memory.overview = "mode again"
        memory.save_to_file()  # the update path replaces the file again
    finally:
        os.umask(old_umask)

    assert memory.path is not None
    memory_mode = stat.S_IMODE(memory.path.stat().st_mode)
    project_mode = stat.S_IMODE((tmp_path / "project.kiln").stat().st_mode)
    assert memory_mode == project_mode == (0o666 & ~umask)
    assert list(memory.path.parent.glob(".tmp-*")) == []


def _replace_failing(times: int, calls: list[str]):
    real_replace = os.replace

    def replace(src, dst):
        calls.append(src)
        if len(calls) <= times:
            raise PermissionError("target is open in another process")
        real_replace(src, dst)

    return replace


def test_save_retries_a_blocked_replace_on_windows(
    project: Project, monkeypatch: pytest.MonkeyPatch
):
    memory = Memory(parent=project, overview="before", scope="project")
    memory.save_to_file()
    calls: list[str] = []
    monkeypatch.setattr(memory_module, "_RETRY_REPLACE", True)
    monkeypatch.setattr(memory_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(memory_module.os, "replace", _replace_failing(2, calls))

    memory.overview = "after"
    memory.save_to_file()

    assert len(calls) == 3
    assert json.loads(memory.path.read_text())["overview"] == "after"
    assert list(memory.path.parent.glob(".tmp-*")) == []


def test_save_does_not_retry_a_blocked_replace_off_windows(
    project: Project, monkeypatch: pytest.MonkeyPatch
):
    memory = Memory(parent=project, overview="before", scope="project")
    memory.save_to_file()
    calls: list[str] = []
    monkeypatch.setattr(memory_module, "_RETRY_REPLACE", False)
    monkeypatch.setattr(memory_module.os, "replace", _replace_failing(1, calls))

    memory.overview = "after"
    with pytest.raises(PermissionError):
        memory.save_to_file()

    assert len(calls) == 1
    assert json.loads(memory.path.read_text())["overview"] == "before"
    assert list(memory.path.parent.glob(".tmp-*")) == []
