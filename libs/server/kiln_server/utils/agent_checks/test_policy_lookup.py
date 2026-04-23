import json
from pathlib import Path

import pytest
from kiln_server.utils.agent_checks.dump_annotations import (
    normalize_endpoint_filename,
)
from kiln_server.utils.agent_checks.policy_lookup import (
    AgentPolicyError,
    AgentPolicyLookup,
)


@pytest.fixture
def annotations_dir(tmp_path: Path) -> Path:
    return tmp_path / "annotations"


def _write_annotation(
    annotations_dir: Path, method: str, path: str, policy: dict | None
) -> None:
    annotations_dir.mkdir(parents=True, exist_ok=True)
    filename = normalize_endpoint_filename(method, path)
    filepath = annotations_dir / filename
    with open(filepath, "w") as f:
        json.dump({"method": method.lower(), "path": path, "agent_policy": policy}, f)


class TestGetPolicy:
    def test_happy_path(self, annotations_dir: Path) -> None:
        _write_annotation(
            annotations_dir,
            "get",
            "/api/projects",
            {"permission": "allow", "requires_approval": False},
        )
        lookup = AgentPolicyLookup(annotations_dir)
        policy = lookup.get_policy("get", "/api/projects")
        assert policy.permission == "allow"
        assert policy.requires_approval is False
        assert policy.approval_description is None

    def test_unknown_endpoint(self, annotations_dir: Path) -> None:
        _write_annotation(
            annotations_dir,
            "get",
            "/api/projects",
            {"permission": "allow", "requires_approval": False},
        )
        lookup = AgentPolicyLookup(annotations_dir)
        with pytest.raises(AgentPolicyError, match="No agent policy found"):
            lookup.get_policy("post", "/api/unknown")

    def test_unannotated_endpoint(self, annotations_dir: Path) -> None:
        _write_annotation(annotations_dir, "get", "/api/projects", None)
        lookup = AgentPolicyLookup(annotations_dir)
        with pytest.raises(AgentPolicyError, match="fail-safe"):
            lookup.get_policy("get", "/api/projects")

    def test_lazy_loading(self, annotations_dir: Path) -> None:
        _write_annotation(
            annotations_dir,
            "get",
            "/api/projects",
            {"permission": "allow", "requires_approval": False},
        )
        lookup = AgentPolicyLookup(annotations_dir)
        assert lookup._cache is None
        lookup.get_policy("get", "/api/projects")
        assert lookup._cache is not None

    def test_preload_populates_cache(self, annotations_dir: Path) -> None:
        _write_annotation(
            annotations_dir,
            "get",
            "/api/projects",
            {"permission": "allow", "requires_approval": False},
        )
        lookup = AgentPolicyLookup(annotations_dir)
        assert lookup._cache is None
        lookup.preload()
        assert lookup._cache is not None
        assert ("get", "/api/projects") in lookup._cache

    def test_preload_missing_dir_raises(self, tmp_path: Path) -> None:
        lookup = AgentPolicyLookup(tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError, match="Annotations directory not found"):
            lookup.preload()

    @pytest.mark.parametrize("method_input", ["GET", "Get", "get"])
    def test_method_case_insensitivity(
        self, annotations_dir: Path, method_input: str
    ) -> None:
        _write_annotation(
            annotations_dir,
            "get",
            "/api/projects",
            {"permission": "allow", "requires_approval": False},
        )
        lookup = AgentPolicyLookup(annotations_dir)
        policy = lookup.get_policy(method_input, "/api/projects")
        assert policy.permission == "allow"

    def test_multiple_endpoints(self, annotations_dir: Path) -> None:
        _write_annotation(
            annotations_dir,
            "get",
            "/api/projects",
            {"permission": "allow", "requires_approval": False},
        )
        _write_annotation(
            annotations_dir,
            "delete",
            "/api/projects/{project_id}",
            {"permission": "deny", "requires_approval": False},
        )
        lookup = AgentPolicyLookup(annotations_dir)
        allow_policy = lookup.get_policy("get", "/api/projects")
        assert allow_policy.permission == "allow"
        deny_policy = lookup.get_policy("delete", "/api/projects/{project_id}")
        assert deny_policy.permission == "deny"

    def test_require_approval_policy(self, annotations_dir: Path) -> None:
        _write_annotation(
            annotations_dir,
            "post",
            "/api/fine-tune",
            {
                "permission": "allow",
                "requires_approval": True,
                "approval_description": "Creating a fine-tune incurs cost.",
            },
        )
        lookup = AgentPolicyLookup(annotations_dir)
        policy = lookup.get_policy("post", "/api/fine-tune")
        assert policy.permission == "allow"
        assert policy.requires_approval is True
        assert policy.approval_description == "Creating a fine-tune incurs cost."

    def test_missing_annotations_dir(self, tmp_path: Path) -> None:
        missing_dir = tmp_path / "nonexistent"
        lookup = AgentPolicyLookup(missing_dir)
        with pytest.raises(FileNotFoundError, match="Annotations directory not found"):
            lookup.get_policy("get", "/api/anything")
