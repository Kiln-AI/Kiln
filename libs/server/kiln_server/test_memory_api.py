from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Memory, Project

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.memory_api import connect_memory_api

BASE = datetime(2026, 7, 1, tzinfo=timezone.utc)


@pytest.fixture
def app():
    app = FastAPI()
    connect_memory_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def project(tmp_path):
    project = Project(
        name="Test Project", path=tmp_path / "test_project" / "project.kiln"
    )
    project.save_to_file()
    return project


def add(project: Project, overview: str, scope: str, minutes: int, **kw) -> Memory:
    """Create a memory directly (explicit created_at) for deterministic ordering."""
    memory = Memory(
        parent=project,
        overview=overview,
        scope=scope,
        created_at=BASE + timedelta(minutes=minutes),
        **kw,
    )
    memory.save_to_file()
    return memory


def _patch(project: Project):
    return patch("kiln_server.memory_api.project_from_id", return_value=project)


# --- save ---


def test_save_memory(client, project):
    with _patch(project):
        resp = client.post(
            f"/api/projects/{project.id}/memories",
            json={"overview": "API X 5rps", "scope": "project", "tags": ["api_quirk"]},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overview"] == "API X 5rps"
    assert data["scope"] == "project"
    assert "id" in data and "created_at" in data
    assert len(project.memories()) == 1


def test_save_missing_scope_is_422(client, project):
    with _patch(project):
        resp = client.post(
            f"/api/projects/{project.id}/memories", json={"overview": "x"}
        )
    assert resp.status_code == 422


def test_save_over_length_overview_is_422(client, project):
    with _patch(project):
        resp = client.post(
            f"/api/projects/{project.id}/memories",
            json={"overview": "a" * 141, "scope": "project"},
        )
    assert resp.status_code == 422


def test_save_newline_overview_is_422(client, project):
    # Newlines aren't expressible in JSON schema; the core validator rejects → 422.
    with _patch(project):
        resp = client.post(
            f"/api/projects/{project.id}/memories",
            json={"overview": "a\nb", "scope": "project"},
        )
    assert resp.status_code == 422


# --- list ---


def test_list_newest_first(client, project):
    add(project, "oldest", "project", 0)
    add(project, "newest", "project", 10)
    with _patch(project):
        resp = client.get(f"/api/projects/{project.id}/memories")
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] == 2
    assert [row["overview"] for row in data["listings"]] == ["newest", "oldest"]


def test_list_scope_and_tags_filters(client, project):
    add(project, "a", "project", 0, tags=["x"])
    add(project, "b", "task::1", 1, tags=["x", "y"])
    with _patch(project):
        by_scope = client.get(
            f"/api/projects/{project.id}/memories", params={"scope": "task::1"}
        )
        by_tags = client.get(
            f"/api/projects/{project.id}/memories", params={"tags": ["x", "y"]}
        )
    assert [r["overview"] for r in by_scope.json()["listings"]] == ["b"]
    assert [r["overview"] for r in by_tags.json()["listings"]] == ["b"]


def test_list_content_length_and_truncation(client, project):
    add(project, "null", "project", 0, tags=["a"])
    add(project, "full", "project", 1, content="12345", tags=["a"])
    add(project, "third", "project", 2, tags=["b"])
    with _patch(project):
        resp = client.get(f"/api/projects/{project.id}/memories", params={"limit": 1})
    data = resp.json()
    assert data["matched"] == 3
    assert data["remaining"] == 2
    assert data["remaining_tag_counts"] == {"a": 2}  # remainder = null + full
    lengths = {r["overview"]: r["content_length"] for r in data["listings"]}
    assert lengths == {"third": 0}


def test_list_content_match(client, project):
    add(project, "has ERROR", "project", 1)
    add(project, "clean", "project", 0, content="body error text")
    add(project, "nope", "project", 2, content="irrelevant")
    with _patch(project):
        resp = client.get(
            f"/api/projects/{project.id}/memories", params={"content_match": "error"}
        )
    assert {r["overview"] for r in resp.json()["listings"]} == {"has ERROR", "clean"}


def test_list_invalid_regex_is_422(client, project):
    with _patch(project):
        resp = client.get(
            f"/api/projects/{project.id}/memories",
            params={"content_match": "[unclosed"},
        )
    assert resp.status_code == 422


@pytest.mark.parametrize("params", [{"limit": -1}, {"limit": 0}, {"offset": -1}])
def test_list_rejects_out_of_range_paging(client, project, params):
    with _patch(project):
        resp = client.get(f"/api/projects/{project.id}/memories", params=params)
    assert resp.status_code == 422


# --- summary ---


def test_summary(client, project):
    add(project, "a", "project", 0, tags=["x"])
    add(project, "b", "task::1", 1)  # untagged
    with _patch(project):
        resp = client.get(f"/api/projects/{project.id}/memories/summary")
    data = resp.json()
    assert data["total"] == 2
    by_scope = {s["scope"]: s for s in data["scopes"]}
    assert by_scope["project"]["count"] == 1
    assert "untagged" not in by_scope["project"]  # zero → excluded
    assert by_scope["task::1"]["untagged"] == 1


# --- get by ids ---


def test_get_by_ids_batch_and_unknown_omitted(client, project):
    a = add(project, "a", "project", 0)
    b = add(project, "b", "project", 1)
    with _patch(project):
        resp = client.get(
            f"/api/projects/{project.id}/memories/by_ids",
            params={"ids": [a.id, b.id, "999999999999"]},
        )
    assert resp.status_code == 200
    assert {r["overview"] for r in resp.json()} == {"a", "b"}


# --- update ---


def test_update_partial_replace(client, project):
    m = add(project, "orig", "project", 0, content="c", tags=["t"])
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}", json={"overview": "changed"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overview"] == "changed"
    assert data["content"] == "c"  # untouched
    assert data["tags"] == ["t"]  # untouched


def test_update_clears_content_with_empty_string(client, project):
    m = add(project, "orig", "project", 0, content="something")
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}", json={"content": ""}
        )
    assert resp.status_code == 200
    assert resp.json()["content"] is None


def test_update_unknown_id_is_404(client, project):
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/999999999999",
            json={"overview": "x"},
        )
    assert resp.status_code == 404


def test_update_over_length_is_422(client, project):
    m = add(project, "orig", "project", 0)
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}",
            json={"overview": "a" * 141},
        )
    assert resp.status_code == 422


# --- delete ---


def test_delete(client, project):
    m = add(project, "junk", "project", 0)
    with _patch(project):
        resp = client.delete(f"/api/projects/{project.id}/memories/{m.id}")
    assert resp.status_code == 200
    assert project.memories() == []


def test_delete_unknown_id_is_404(client, project):
    with _patch(project):
        resp = client.delete(f"/api/projects/{project.id}/memories/999999999999")
    assert resp.status_code == 404


# --- agent policy ---


def test_all_endpoints_allow_agent(app):
    """All six memory endpoints are agent-allowed with no approval gate (decision 11)."""
    paths = app.openapi()["paths"]
    memory_ops = [
        (method, path, op.get("x-agent-policy"))
        for path, item in paths.items()
        if "/memories" in path
        for method, op in item.items()
    ]
    assert len(memory_ops) == 6
    for method, path, policy in memory_ops:
        assert policy == {"permission": "allow", "requires_approval": False}, (
            method,
            path,
        )
