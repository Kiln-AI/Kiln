from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kiln_ai.datamodel import Memory, Project
from kiln_ai.memory import (
    InvalidContentMatchError,
    MemoryNotFoundError,
    MemoryStore,
)

BASE = datetime(2026, 7, 1, tzinfo=timezone.utc)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    project = Project(name="store_test", path=tmp_path / "project.kiln")
    project.save_to_file()
    return project


@pytest.fixture
def store(project: Project) -> MemoryStore:
    return MemoryStore(project)


def add(project: Project, overview: str, scope: str, minutes: int, **kw) -> Memory:
    """Create a memory with an explicit created_at (for deterministic ordering)."""
    memory = Memory(
        parent=project,
        overview=overview,
        scope=scope,
        created_at=BASE + timedelta(minutes=minutes),
        **kw,
    )
    memory.save_to_file()
    return memory


# --- construction ---


def test_requires_saved_parent(tmp_path: Path):
    unsaved = Project(name="unsaved")  # no path
    with pytest.raises(ValueError):
        MemoryStore(unsaved)


# --- save ---


def test_save_returns_id_and_writes_file(store: MemoryStore):
    memory = store.save_memory(overview="hello", scope="project", tags=["t"])
    assert memory.id is not None
    assert memory.path is not None and memory.path.exists()
    assert store.get_memories([memory.id])[0].overview == "hello"


# --- list ---


def test_list_newest_first(project: Project, store: MemoryStore):
    add(project, "oldest", "project", minutes=0)
    add(project, "middle", "project", minutes=10)
    add(project, "newest", "project", minutes=20)
    result = store.list_memories()
    assert [row.overview for row in result.listings] == ["newest", "middle", "oldest"]


def test_list_scope_exact_filter(project: Project, store: MemoryStore):
    add(project, "a", "project", minutes=0)
    add(project, "b", "task::1", minutes=1)
    add(project, "c", "task::10", minutes=2)
    result = store.list_memories(scope="task::1")
    assert [row.overview for row in result.listings] == ["b"]


def test_list_tags_and_semantics(project: Project, store: MemoryStore):
    add(project, "both", "project", minutes=2, tags=["x", "y"])
    add(project, "only_x", "project", minutes=1, tags=["x"])
    add(project, "none", "project", minutes=0, tags=[])
    result = store.list_memories(tags=["x", "y"])
    assert [row.overview for row in result.listings] == ["both"]


def test_list_content_match_case_insensitive_over_overview_and_content(
    project: Project, store: MemoryStore
):
    add(project, "overview has ERROR", "project", minutes=2)
    add(project, "clean overview", "project", minutes=1, content="body has error text")
    add(project, "no match", "project", minutes=0, content="nothing relevant")
    result = store.list_memories(content_match="error")
    assert {row.overview for row in result.listings} == {
        "overview has ERROR",
        "clean overview",
    }


def test_list_limit_offset(project: Project, store: MemoryStore):
    for i in range(5):
        add(project, f"m{i}", "project", minutes=i)  # m4 newest
    result = store.list_memories(limit=2, offset=1)
    # newest-first: [m4, m3, m2, m1, m0]; offset 1, limit 2 -> [m3, m2]
    assert [row.overview for row in result.listings] == ["m3", "m2"]


def test_list_content_length(project: Project, store: MemoryStore):
    add(project, "null content", "project", minutes=1)
    add(project, "has content", "project", minutes=0, content="12345")
    by_overview = {
        row.overview: row.content_length for row in store.list_memories().listings
    }
    assert by_overview["null content"] == 0
    assert by_overview["has content"] == 5


def test_list_truncation_remaining_and_tag_counts(project: Project, store: MemoryStore):
    add(project, "m0", "project", minutes=0, tags=["a"])
    add(project, "m1", "project", minutes=1, tags=["a", "b"])
    add(project, "m2", "project", minutes=2, tags=["b"])
    add(project, "m3", "project", minutes=3, tags=["c"])
    add(project, "m4", "project", minutes=4, tags=["c"])
    result = store.list_memories(limit=2)
    # page = [m4, m3]; remainder = [m2, m1, m0]
    assert [row.overview for row in result.listings] == ["m4", "m3"]
    assert result.matched == 5
    assert result.remaining == 3
    assert result.remaining_tag_counts == {"a": 2, "b": 2}


def test_list_no_truncation_when_page_covers_matched(
    project: Project, store: MemoryStore
):
    add(project, "m0", "project", minutes=0, tags=["a"])
    add(project, "m1", "project", minutes=1, tags=["b"])
    result = store.list_memories(limit=10)
    assert result.matched == 2
    assert result.remaining == 0
    assert result.remaining_tag_counts == {}


def test_list_invalid_regex_raises(store: MemoryStore):
    with pytest.raises(InvalidContentMatchError):
        store.list_memories(content_match="[unclosed")


# --- get ---


def test_get_single_and_many(project: Project, store: MemoryStore):
    a = add(project, "a", "project", minutes=0)
    b = add(project, "b", "project", minutes=1)
    assert {m.overview for m in store.get_memories([a.id])} == {"a"}
    assert {m.overview for m in store.get_memories([a.id, b.id])} == {"a", "b"}


def test_get_unknown_ids_omitted(project: Project, store: MemoryStore):
    a = add(project, "a", "project", minutes=0)
    got = store.get_memories([a.id, "999999999999"])
    assert {m.overview for m in got} == {"a"}


# --- update ---


def test_update_partial_replace_only_provided(project: Project, store: MemoryStore):
    memory = add(project, "orig", "project", minutes=0, content="c", tags=["t"])
    store.update_memory(memory.id, overview="changed")
    got = store.get_memories([memory.id])[0]
    assert got.overview == "changed"
    assert got.content == "c"  # untouched
    assert got.tags == ["t"]  # untouched
    assert got.scope == "project"  # untouched


def test_update_revalidates_provided_field(project: Project, store: MemoryStore):
    memory = add(project, "orig", "project", minutes=0)
    with pytest.raises(Exception):
        store.update_memory(memory.id, overview="a" * 141)


def test_update_content_empty_clears_to_none(project: Project, store: MemoryStore):
    memory = add(project, "orig", "project", minutes=0, content="something")
    store.update_memory(memory.id, content="")
    assert store.get_memories([memory.id])[0].content is None


def test_update_unknown_id_raises(store: MemoryStore):
    with pytest.raises(MemoryNotFoundError):
        store.update_memory("999999999999", overview="x")


def test_update_last_writer_wins(project: Project, store: MemoryStore):
    memory = add(project, "orig", "project", minutes=0)
    store.update_memory(memory.id, overview="first")
    store.update_memory(memory.id, overview="second")
    assert store.get_memories([memory.id])[0].overview == "second"


# --- delete ---


def test_delete_removes_folder(project: Project, store: MemoryStore):
    memory = add(project, "junk", "project", minutes=0)
    folder = memory.path.parent
    store.delete_memory(memory.id)
    assert not folder.exists()
    assert store.list_memories().matched == 0


def test_delete_unknown_id_raises(store: MemoryStore):
    with pytest.raises(MemoryNotFoundError):
        store.delete_memory("999999999999")


# --- summary ---


def test_summary_per_scope_grouping(project: Project, store: MemoryStore):
    add(project, "a", "project", minutes=0)
    add(project, "b", "task::1", minutes=1)
    add(project, "c", "task::1", minutes=2)
    summary = store.memory_summary()
    assert summary.total == 3
    by_scope = {s.scope: s for s in summary.scopes}
    assert by_scope["project"].count == 1
    assert by_scope["task::1"].count == 2


def test_summary_tag_counts_desc(project: Project, store: MemoryStore):
    add(project, "a", "project", minutes=0, tags=["x"])
    add(project, "b", "project", minutes=1, tags=["x"])
    add(project, "c", "project", minutes=2, tags=["x", "y"])
    add(project, "d", "project", minutes=3, tags=["y"])  # x=3, y=2
    tags = store.memory_summary().scopes[0].tags
    assert list(tags.items()) == [("x", 3), ("y", 2)]


def test_summary_untagged_only_when_nonzero(project: Project, store: MemoryStore):
    add(project, "tagged", "tagged_scope", minutes=1, tags=["x"])
    add(project, "untagged", "untagged_scope", minutes=0)
    by_scope = {s.scope: s for s in store.memory_summary().scopes}
    assert by_scope["tagged_scope"].untagged is None
    assert by_scope["untagged_scope"].untagged == 1


def test_summary_scopes_newest_first(project: Project, store: MemoryStore):
    add(project, "old", "old_scope", minutes=0)
    add(project, "new", "new_scope", minutes=10)
    assert [s.scope for s in store.memory_summary().scopes] == [
        "new_scope",
        "old_scope",
    ]


def test_summary_scoped_call_single_block(project: Project, store: MemoryStore):
    add(project, "a", "project", minutes=0)
    add(project, "b", "task::1", minutes=1)
    summary = store.memory_summary(scope="project")
    assert summary.total == 1
    assert [s.scope for s in summary.scopes] == ["project"]


def test_summary_newest_timestamp(project: Project, store: MemoryStore):
    add(project, "old", "project", minutes=0)
    newest = add(project, "new", "project", minutes=30)
    assert store.memory_summary().scopes[0].newest == newest.created_at


def test_summary_untagged_serialization_excluded(project: Project, store: MemoryStore):
    add(project, "tagged", "project", minutes=0, tags=["x"])
    dumped = store.memory_summary().model_dump(mode="json", exclude_none=True)
    assert "untagged" not in dumped["scopes"][0]
