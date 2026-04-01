import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from kiln_server.utils.agent_checks.dump_annotations import (
    dump_annotations,
    load_openapi_spec,
    main,
    normalize_endpoint_filename,
)

# -- normalize_endpoint_filename tests --


@pytest.mark.parametrize(
    "method, path, expected",
    [
        ("GET", "/api/health", "get_api_health.json"),
        (
            "POST",
            "/api/projects/{project_id}/tasks",
            "post_api_projects_project_id_tasks.json",
        ),
        ("DELETE", "/api/items/{id}", "delete_api_items_id.json"),
        ("PATCH", "/api/a/b/c/d", "patch_api_a_b_c_d.json"),
        ("get", "/api/health", "get_api_health.json"),
        (
            "POST",
            "/api/{org_id}/projects/{project_id}",
            "post_api_org_id_projects_project_id.json",
        ),
    ],
)
def test_normalize_endpoint_filename(method: str, path: str, expected: str) -> None:
    assert normalize_endpoint_filename(method, path) == expected


# -- Fixtures --


def _make_spec(paths: dict) -> dict:
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": paths,
    }


@pytest.fixture
def annotated_spec() -> dict:
    return _make_spec(
        {
            "/api/health": {
                "get": {
                    "summary": "Health check",
                    "x-agent-policy": {
                        "permission": "allow",
                        "requires_approval": False,
                    },
                }
            },
            "/api/items": {
                "post": {
                    "summary": "Create item",
                    "x-agent-policy": {
                        "permission": "allow",
                        "requires_approval": True,
                        "approval_description": "Allow creating items?",
                    },
                }
            },
        }
    )


@pytest.fixture
def unannotated_spec() -> dict:
    return _make_spec(
        {
            "/api/health": {
                "get": {
                    "summary": "Health check",
                    "x-agent-policy": {
                        "permission": "allow",
                        "requires_approval": False,
                    },
                }
            },
            "/api/items": {
                "post": {"summary": "Create item"},
            },
        }
    )


@pytest.fixture
def invalid_policy_spec() -> dict:
    return _make_spec(
        {
            "/api/bad": {
                "get": {
                    "summary": "Bad endpoint",
                    "x-agent-policy": {"permission": "deny", "requires_approval": True},
                }
            },
        }
    )


# -- load_openapi_spec tests --


def test_load_from_file(tmp_path: Path) -> None:
    spec = {"openapi": "3.0.0", "paths": {}}
    filepath = os.path.join(str(tmp_path), "spec.json")
    with open(filepath, "w") as f:
        json.dump(spec, f)
    result = load_openapi_spec(filepath)
    assert result == spec


def test_load_from_url() -> None:
    spec = {"openapi": "3.0.0", "paths": {}}
    mock_response = MagicMock()
    mock_response.json.return_value = spec

    with patch("httpx.get", return_value=mock_response) as mock_get:
        result = load_openapi_spec("http://localhost:8757/openapi.json")

    mock_get.assert_called_once_with("http://localhost:8757/openapi.json")
    mock_response.raise_for_status.assert_called_once()
    assert result == spec


# -- dump_annotations tests --


def test_dump_all_annotated(tmp_path: Path, annotated_spec: dict) -> None:
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(annotated_spec, f)

    exit_code = dump_annotations(spec_file, target)

    assert exit_code == 0

    health_file = os.path.join(target, "get_api_health.json")
    with open(health_file) as f:
        data = json.load(f)
    assert data["method"] == "get"
    assert data["path"] == "/api/health"
    assert data["agent_policy"]["permission"] == "allow"
    assert data["agent_policy"]["requires_approval"] is False

    items_file = os.path.join(target, "post_api_items.json")
    with open(items_file) as f:
        data = json.load(f)
    assert data["agent_policy"]["requires_approval"] is True
    assert data["agent_policy"]["approval_description"] == "Allow creating items?"


def test_dump_unannotated(
    tmp_path: Path, unannotated_spec: dict, caplog: pytest.LogCaptureFixture
) -> None:
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(unannotated_spec, f)

    exit_code = dump_annotations(spec_file, target)

    assert exit_code == 2
    assert "1 unannotated endpoint(s)" in caplog.text
    assert "POST /api/items" in caplog.text

    items_file = os.path.join(target, "post_api_items.json")
    with open(items_file) as f:
        data = json.load(f)
    assert data["agent_policy"] is None


def test_dump_invalid_policy(
    tmp_path: Path, invalid_policy_spec: dict, caplog: pytest.LogCaptureFixture
) -> None:
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(invalid_policy_spec, f)

    exit_code = dump_annotations(spec_file, target)

    assert exit_code == 2
    assert "Invalid policy on GET /api/bad" in caplog.text

    bad_file = os.path.join(target, "get_api_bad.json")
    with open(bad_file) as f:
        data = json.load(f)
    assert data["agent_policy"] is None


def test_dump_empty_spec(tmp_path: Path) -> None:
    spec = _make_spec({})
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(spec, f)

    exit_code = dump_annotations(spec_file, target)

    assert exit_code == 0


def test_dump_creates_target_dir(tmp_path: Path, annotated_spec: dict) -> None:
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "nested", "output")
    with open(spec_file, "w") as f:
        json.dump(annotated_spec, f)

    exit_code = dump_annotations(spec_file, target)

    assert exit_code == 0
    assert os.path.isdir(target)


def test_dump_multiple_methods_same_path(tmp_path: Path) -> None:
    spec = _make_spec(
        {
            "/api/items": {
                "get": {
                    "summary": "List",
                    "x-agent-policy": {
                        "permission": "allow",
                        "requires_approval": False,
                    },
                },
                "post": {
                    "summary": "Create",
                    "x-agent-policy": {
                        "permission": "allow",
                        "requires_approval": False,
                    },
                },
            }
        }
    )
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(spec, f)

    exit_code = dump_annotations(spec_file, target)

    assert exit_code == 0
    assert os.path.exists(os.path.join(target, "get_api_items.json"))
    assert os.path.exists(os.path.join(target, "post_api_items.json"))


# -- main entry point tests --


def test_main_entrypoint(tmp_path: Path, annotated_spec: dict) -> None:
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(annotated_spec, f)

    with patch("sys.argv", ["dump_annotations", spec_file, target]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


def test_main_entrypoint_unannotated(tmp_path: Path, unannotated_spec: dict) -> None:
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(unannotated_spec, f)

    with patch("sys.argv", ["dump_annotations", spec_file, target]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
