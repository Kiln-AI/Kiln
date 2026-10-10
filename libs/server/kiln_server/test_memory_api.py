import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Memory, Project
from kiln_ai.datamodel.memory import MAX_CONTENT_LENGTH, MAX_OVERVIEW_LENGTH

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
            json={"overview": "a" * (MAX_OVERVIEW_LENGTH + 1), "scope": "project"},
        )
    assert resp.status_code == 422
    error = resp.json()["source_errors"][0]
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == str(MAX_OVERVIEW_LENGTH)
    assert len(project.memories()) == 0


def test_save_over_length_content_is_422(client, project):
    with _patch(project):
        resp = client.post(
            f"/api/projects/{project.id}/memories",
            json={
                "overview": "x",
                "scope": "project",
                "content": "a" * (MAX_CONTENT_LENGTH + 1),
            },
        )
    assert resp.status_code == 422
    error = resp.json()["source_errors"][0]
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == str(MAX_CONTENT_LENGTH)
    assert len(project.memories()) == 0


def test_save_accepts_exactly_max_lengths(client, project):
    with _patch(project):
        resp = client.post(
            f"/api/projects/{project.id}/memories",
            json={
                "overview": "a" * MAX_OVERVIEW_LENGTH,
                "scope": "project",
                "content": "b" * MAX_CONTENT_LENGTH,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["overview"]) == MAX_OVERVIEW_LENGTH
    assert len(data["content"]) == MAX_CONTENT_LENGTH


_CORE_VALIDATION_CASES = [
    ({"overview": "a\nb"}, "overview"),
    ({"scope": "   "}, "scope"),
    ({"tags": ["a b"]}, "tags"),
]


@pytest.mark.parametrize("bad, field", _CORE_VALIDATION_CASES)
def test_save_core_validation_is_422_naming_the_field(client, project, bad, field):
    # These rules live in the Memory model, not the request model. Their 422
    # must have the same body as a request-model 422.
    with _patch(project):
        resp = client.post(
            f"/api/projects/{project.id}/memories",
            json={"overview": "x", "scope": "project", **bad},
        )
    assert resp.status_code == 422
    data = resp.json()
    assert data["source_errors"][0]["loc"][0] == field
    assert data["message"].startswith(field.capitalize())
    assert len(project.memories()) == 0


@pytest.mark.parametrize("bad, field", _CORE_VALIDATION_CASES)
def test_update_core_validation_is_422_naming_the_field(client, project, bad, field):
    m = add(project, "orig", "project", 0, tags=["t"])
    with _patch(project):
        resp = client.patch(f"/api/projects/{project.id}/memories/{m.id}", json=bad)
    assert resp.status_code == 422
    data = resp.json()
    assert data["source_errors"][0]["loc"][0] == field
    assert data["message"].startswith(field.capitalize())
    stored = project.memories()[0]
    assert (stored.overview, stored.scope, stored.tags) == ("orig", "project", ["t"])


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


def test_list_catastrophic_regex_is_422(client, project):
    # Nested quantifiers backtrack for an exponential time on this content.
    add(
        project,
        "slow note.",
        "project",
        0,
        content="a" * (MAX_CONTENT_LENGTH - 1) + "!",
    )
    # The regex timeout counts CPU time, so this test does too. Wall time on a
    # loaded test machine is not stable.
    start = time.process_time()
    with _patch(project):
        resp = client.get(
            f"/api/projects/{project.id}/memories",
            params={"content_match": r"(\w+\s?)+$"},
        )
    assert time.process_time() - start < 2
    assert resp.status_code == 422
    assert "too expensive" in resp.json()["message"]


def test_list_escaped_text_content_match(client, project):
    add(project, "cost", "project", 1, content="Total: $5.00 (approx) [est]?")
    add(project, "other", "project", 0, content="Total: 5 dollars")
    with _patch(project):
        resp = client.get(
            f"/api/projects/{project.id}/memories",
            params={"content_match": re.escape("$5.00 (approx) [est]?")},
        )
    assert resp.status_code == 200
    assert [r["overview"] for r in resp.json()["listings"]] == ["cost"]


@pytest.mark.parametrize("params", [{"limit": -1}, {"limit": 0}, {"offset": -1}])
def test_list_rejects_out_of_range_paging(client, project, params):
    with _patch(project):
        resp = client.get(f"/api/projects/{project.id}/memories", params=params)
    assert resp.status_code == 422


def test_list_includes_stored_178_char_overview_row(client, project):
    """Regression: a stored row with a 178-char overview (written when the write
    path didn't stop it) used to fail load validation under the old 140 cap and
    422 every listing. Plant the row raw on disk — bypassing write validation,
    like the original writer — and verify it now lists and fetches fine."""
    long_overview = "x" * 178
    memory_dir = project.path.parent / "assistant_memory" / "999888777666"
    memory_dir.mkdir(parents=True)
    (memory_dir / "memory.kiln").write_text(
        json.dumps(
            {
                "v": 1,
                "id": "999888777666",
                "created_at": BASE.isoformat(),
                "created_by": "agent",
                "model_type": "memory",
                "overview": long_overview,
                "content": None,
                "tags": [],
                "scope": "project",
            },
            ensure_ascii=False,
        )
    )

    with _patch(project):
        listed = client.get(f"/api/projects/{project.id}/memories")
        fetched = client.get(
            f"/api/projects/{project.id}/memories/by_ids",
            params={"ids": ["999888777666"]},
        )
    assert listed.status_code == 200
    assert [r["overview"] for r in listed.json()["listings"]] == [long_overview]
    assert fetched.status_code == 200
    assert fetched.json()[0]["overview"] == long_overview


def test_by_id_endpoints_skip_an_unreadable_memory(client, project):
    good = add(project, "good", "project", 0)
    doomed = add(project, "doomed", "project", 1)
    bad = add(project, "bad", "project", 2)
    bad.path.write_text("{ not json", encoding="utf-8")

    with _patch(project):
        fetched = client.get(
            f"/api/projects/{project.id}/memories/by_ids",
            params={"ids": [good.id, bad.id]},
        )
        patched = client.patch(
            f"/api/projects/{project.id}/memories/{good.id}",
            json={"overview": "edited"},
        )
        deleted = client.delete(f"/api/projects/{project.id}/memories/{doomed.id}")
        bad_patch = client.patch(
            f"/api/projects/{project.id}/memories/{bad.id}", json={"overview": "x"}
        )

    assert fetched.status_code == 200
    assert [r["id"] for r in fetched.json()] == [good.id]
    assert patched.status_code == 200
    assert patched.json()["overview"] == "edited"
    assert deleted.status_code == 200
    assert bad_patch.status_code == 404


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


@pytest.mark.parametrize("field, cleared", [("content", None), ("tags", [])])
def test_update_null_clears_content_and_tags(client, project, field, cleared):
    m = add(project, "orig", "project", 0, content="body", tags=["t"])
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}", json={field: None}
        )
    assert resp.status_code == 200
    assert resp.json()[field] == cleared
    assert getattr(project.memories()[0], field) == cleared


@pytest.mark.parametrize("field", ["overview", "scope"])
def test_update_null_overview_or_scope_is_422(client, project, field):
    m = add(project, "orig", "project", 0)
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}", json={field: None}
        )
    assert resp.status_code == 422
    assert resp.json()["source_errors"][0]["loc"][0] == field
    stored = project.memories()[0]
    assert (stored.overview, stored.scope) == ("orig", "project")


def test_update_unknown_id_is_404(client, project):
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/999999999999",
            json={"overview": "x"},
        )
    assert resp.status_code == 404


def test_update_over_length_overview_is_422(client, project):
    m = add(project, "orig", "project", 0)
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}",
            json={"overview": "a" * (MAX_OVERVIEW_LENGTH + 1)},
        )
    assert resp.status_code == 422
    error = resp.json()["source_errors"][0]
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == str(MAX_OVERVIEW_LENGTH)
    assert project.memories()[0].overview == "orig"


def test_update_over_length_content_is_422(client, project):
    m = add(project, "orig", "project", 0)
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}",
            json={"content": "a" * (MAX_CONTENT_LENGTH + 1)},
        )
    assert resp.status_code == 422
    error = resp.json()["source_errors"][0]
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == str(MAX_CONTENT_LENGTH)
    assert project.memories()[0].content is None


def test_update_accepts_exactly_max_lengths(client, project):
    m = add(project, "orig", "project", 0)
    with _patch(project):
        resp = client.patch(
            f"/api/projects/{project.id}/memories/{m.id}",
            json={
                "overview": "a" * MAX_OVERVIEW_LENGTH,
                "content": "b" * MAX_CONTENT_LENGTH,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["overview"]) == MAX_OVERVIEW_LENGTH
    assert len(data["content"]) == MAX_CONTENT_LENGTH


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


# --- threading ---


@pytest.mark.parametrize(
    "method, suffix, body",
    [
        ("POST", "", {"overview": "new", "scope": "project"}),
        ("GET", "", None),
        ("GET", "/summary", None),
        ("GET", "/by_ids?ids={id}", None),
        ("PATCH", "/{id}", {"overview": "edited"}),
        ("DELETE", "/{id}", None),
    ],
)
def test_handlers_run_the_store_off_the_event_loop(
    client, project, method, suffix, body
):
    """Every handler loads the project and calls the store in a worker thread,
    where no event loop is running, so disk scans never block the loop."""
    memory = add(project, "existing", "project", 0)
    on_loop: list[bool] = []

    def fake_project_from_id(_project_id):
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)
        return project

    url = f"/api/projects/{project.id}/memories" + suffix.format(id=memory.id)
    with patch(
        "kiln_server.memory_api.project_from_id", side_effect=fake_project_from_id
    ):
        resp = client.request(method, url, json=body)

    assert resp.status_code == 200, resp.text
    assert on_loop == [False]
