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


def _make_spec(paths: dict, components_schemas: dict | None = None) -> dict:
    spec: dict = {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": paths,
    }
    if components_schemas is not None:
        spec["components"] = {"schemas": components_schemas}
    return spec


_ALLOW = {"permission": "allow", "requires_approval": False}


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
    assert data["request_body"] is None
    assert data["parameters"] == {"path": {}, "query": {}}

    items_file = os.path.join(target, "post_api_items.json")
    with open(items_file) as f:
        data = json.load(f)
    assert data["agent_policy"]["requires_approval"] is True
    assert data["agent_policy"]["approval_description"] == "Allow creating items?"
    assert data["request_body"] is None
    assert data["parameters"] == {"path": {}, "query": {}}


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


# -- request_body + parameters tests --


def _dump_single(tmp_path: Path, spec: dict) -> dict:
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(spec, f)
    exit_code = dump_annotations(spec_file, target)
    assert exit_code == 0
    (filepath,) = [
        os.path.join(target, f) for f in os.listdir(target) if f.endswith(".json")
    ]
    with open(filepath) as f:
        return json.load(f)


def test_dump_bodyless_get_emits_null_request_body_and_empty_params(
    tmp_path: Path,
) -> None:
    spec = _make_spec(
        {"/api/ping": {"get": {"summary": "ping", "x-agent-policy": _ALLOW}}}
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"] is None
    assert data["parameters"] == {"path": {}, "query": {}}


def test_dump_get_with_path_parameters(tmp_path: Path) -> None:
    spec = _make_spec(
        {
            "/api/items/{item_id}": {
                "get": {
                    "x-agent-policy": _ALLOW,
                    "parameters": [
                        {
                            "name": "item_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["parameters"]["path"] == {"item_id": {"type": "integer"}}
    assert data["parameters"]["query"] == {}


def test_dump_get_with_query_parameter_integer(tmp_path: Path) -> None:
    spec = _make_spec(
        {
            "/api/items": {
                "get": {
                    "x-agent-policy": _ALLOW,
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 10},
                        }
                    ],
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["parameters"]["query"] == {"limit": {"type": "integer", "default": 10}}


def test_dump_get_ignores_header_and_cookie_parameters(tmp_path: Path) -> None:
    spec = _make_spec(
        {
            "/api/items": {
                "get": {
                    "x-agent-policy": _ALLOW,
                    "parameters": [
                        {
                            "name": "X-Trace-Id",
                            "in": "header",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "session",
                            "in": "cookie",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer"},
                        },
                    ],
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["parameters"] == {
        "path": {},
        "query": {"limit": {"type": "integer"}},
    }


def test_dump_post_inlines_component_ref_in_request_body(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Item-Input"}
                            }
                        },
                    },
                }
            }
        },
        components_schemas={
            "Item-Input": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        },
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"]["required"] is True
    assert data["request_body"]["content_type"] == "application/json"
    assert data["request_body"]["schema"] == {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }


def test_dump_post_inlines_nested_ref_inside_anyOf(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "anyOf": [
                                        {"$ref": "#/components/schemas/Inner"},
                                        {"type": "null"},
                                    ]
                                }
                            }
                        },
                    },
                }
            }
        },
        components_schemas={
            "Inner": {"type": "object", "properties": {"n": {"type": "integer"}}}
        },
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"]["schema"] == {
        "anyOf": [
            {"type": "object", "properties": {"n": {"type": "integer"}}},
            {"type": "null"},
        ]
    }


def test_dump_post_inlines_ref_inside_array_items(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Leaf"},
                                }
                            }
                        },
                    },
                }
            }
        },
        components_schemas={"Leaf": {"type": "string"}},
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"]["schema"] == {
        "type": "array",
        "items": {"type": "string"},
    }


def test_dump_post_preserves_additionalProperties_false(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Strict"}
                            }
                        }
                    },
                }
            }
        },
        components_schemas={
            "Strict": {
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                "additionalProperties": False,
            }
        },
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"]["schema"]["additionalProperties"] is False


def test_dump_post_preserves_additionalProperties_when_absent(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Loose"}
                            }
                        }
                    },
                }
            }
        },
        components_schemas={
            "Loose": {"type": "object", "properties": {"n": {"type": "integer"}}}
        },
    )
    data = _dump_single(tmp_path, spec)
    assert "additionalProperties" not in data["request_body"]["schema"]


def test_dump_self_referential_body_uses_local_defs(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/trees": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Node"}
                            }
                        }
                    },
                }
            }
        },
        components_schemas={
            "Node": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Node"},
                    },
                },
            }
        },
    )
    data = _dump_single(tmp_path, spec)
    schema = data["request_body"]["schema"]
    assert schema["$ref"] == "#/$defs/Node"
    assert "Node" in schema["$defs"]
    assert schema["$defs"]["Node"]["properties"]["children"]["items"] == {
        "$ref": "#/$defs/Node"
    }


def test_dump_mutually_recursive_models(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/a": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/A"}
                            }
                        }
                    },
                }
            }
        },
        components_schemas={
            "A": {
                "type": "object",
                "properties": {"b": {"$ref": "#/components/schemas/B"}},
            },
            "B": {
                "type": "object",
                "properties": {"a": {"$ref": "#/components/schemas/A"}},
            },
        },
    )
    data = _dump_single(tmp_path, spec)
    schema = data["request_body"]["schema"]
    assert schema["$ref"] == "#/$defs/A"
    assert "A" in schema["$defs"]
    # B is inlined inside A (only A forms a back-edge to the entry point).
    a_def = schema["$defs"]["A"]
    assert a_def["properties"]["b"]["type"] == "object"
    assert a_def["properties"]["b"]["properties"]["a"] == {"$ref": "#/$defs/A"}


def test_dump_non_cyclic_body_has_no_defs_key(tmp_path: Path) -> None:
    spec = _make_spec(
        paths={
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Flat"}
                            }
                        }
                    },
                }
            }
        },
        components_schemas={
            "Flat": {"type": "object", "properties": {"n": {"type": "integer"}}}
        },
    )
    data = _dump_single(tmp_path, spec)
    assert "$defs" not in data["request_body"]["schema"]


@pytest.mark.parametrize("required", [True, False])
def test_dump_request_body_required_flag_propagates(
    tmp_path: Path, required: bool
) -> None:
    spec = _make_spec(
        paths={
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "required": required,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"]["required"] is required


def test_dump_request_body_missing_content_emits_null(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = _make_spec(
        {
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {"required": True},
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"] is None
    assert "no content on POST /api/items" in caplog.text


def test_dump_request_body_non_json_content_type_emits_null(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = _make_spec(
        {
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {"text/plain": {"schema": {"type": "string"}}}
                    },
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"] is None
    assert "no application/json content" in caplog.text


def test_dump_top_level_request_body_ref_emits_null(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = _make_spec(
        {
            "/api/items": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {"$ref": "#/components/requestBodies/ItemBody"},
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["request_body"] is None
    assert "Top-level requestBody $ref" in caplog.text


def test_dump_unknown_ref_warns_but_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = _make_spec(
        paths={
            "/api/bad": {
                "post": {
                    "x-agent-policy": _ALLOW,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Missing"}
                            }
                        }
                    },
                }
            },
            "/api/good": {"get": {"x-agent-policy": _ALLOW}},
        },
        components_schemas={},
    )
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(spec, f)

    exit_code = dump_annotations(spec_file, target)

    assert exit_code == 0
    assert "Failed to extract request body on POST /api/bad" in caplog.text
    with open(os.path.join(target, "post_api_bad.json")) as f:
        bad = json.load(f)
    assert bad["request_body"] is None
    with open(os.path.join(target, "get_api_good.json")) as f:
        good = json.load(f)
    assert good["method"] == "get"


def test_dump_parameter_missing_schema_warns_and_emits_empty_dict(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = _make_spec(
        {
            "/api/items/{id}": {
                "get": {
                    "x-agent-policy": _ALLOW,
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                }
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["parameters"]["path"] == {"id": {}}
    assert "has no schema" in caplog.text


def test_dump_path_item_parameters_included(tmp_path: Path) -> None:
    spec = _make_spec(
        {
            "/api/items/{id}": {
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {"x-agent-policy": _ALLOW},
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["parameters"]["path"] == {"id": {"type": "string"}}


def test_dump_operation_parameter_overrides_path_item(tmp_path: Path) -> None:
    spec = _make_spec(
        {
            "/api/items/{id}": {
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "x-agent-policy": _ALLOW,
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                },
            }
        }
    )
    data = _dump_single(tmp_path, spec)
    assert data["parameters"]["path"]["id"] == {"type": "integer"}


def test_dump_output_key_order(tmp_path: Path) -> None:
    spec = _make_spec({"/api/items": {"get": {"x-agent-policy": _ALLOW}}})
    spec_file = os.path.join(str(tmp_path), "spec.json")
    target = os.path.join(str(tmp_path), "output")
    with open(spec_file, "w") as f:
        json.dump(spec, f)
    dump_annotations(spec_file, target)
    with open(os.path.join(target, "get_api_items.json")) as f:
        raw = f.read()
    # Keys appear in this exact order in the file.
    idx_method = raw.index('"method"')
    idx_path = raw.index('"path"')
    idx_policy = raw.index('"agent_policy"')
    idx_body = raw.index('"request_body"')
    idx_params = raw.index('"parameters"')
    assert idx_method < idx_path < idx_policy < idx_body < idx_params


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
