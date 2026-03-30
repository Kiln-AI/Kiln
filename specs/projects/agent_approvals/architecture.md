---
status: complete
---

# Architecture: Agent Approvals

## Module Structure

All code lives in `libs/server/kiln_server/utils/agent_checks/`:

```
agent_checks/
  __init__.py              # Exports: AgentPolicy, DENY_AGENT, ALLOW_AGENT,
                           #          agent_policy_require_approval,
                           #          AgentPolicyLookup, AgentPolicyError
  policy.py                # AgentPolicy model + constructors
  dump_annotations.py      # CLI for dumping annotation JSONs
  policy_lookup.py         # AgentPolicyLookup class
  test_policy.py           # Tests for policy model + constructors
  test_dump_annotations.py # Tests for CLI
  test_policy_lookup.py    # Tests for lookup class
```

## Component 1: Policy Model (`policy.py`)

### AgentPolicy

```python
from pydantic import BaseModel, model_validator
from typing import Literal

class AgentPolicy(BaseModel):
    permission: Literal["allow", "deny"]
    requires_approval: bool
    approval_description: str | None = None

    @model_validator(mode="after")
    def validate_approval_fields(self) -> "AgentPolicy":
        if self.permission == "deny" and self.requires_approval:
            raise ValueError("Denied endpoints cannot require approval")
        if self.requires_approval and not self.approval_description:
            raise ValueError("approval_description is required when requires_approval is True")
        if not self.requires_approval and self.approval_description is not None:
            raise ValueError("approval_description must be None when requires_approval is False")
        return self
```

### Constants and Constructor

```python
_DENY_POLICY = AgentPolicy(permission="deny", requires_approval=False)
_ALLOW_POLICY = AgentPolicy(permission="allow", requires_approval=False)

DENY_AGENT: dict = {"x-agent-policy": _DENY_POLICY.model_dump()}
ALLOW_AGENT: dict = {"x-agent-policy": _ALLOW_POLICY.model_dump()}

def agent_policy_require_approval(description: str) -> dict:
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")
    policy = AgentPolicy(
        permission="allow",
        requires_approval=True,
        approval_description=description,
    )
    return {"x-agent-policy": policy.model_dump()}
```

The constants are eagerly constructed (they're simple, no reason to defer). The function validates via the model constructor — no duplicate validation logic.

### `__init__.py` Exports

```python
from kiln_server.utils.agent_checks.policy import (
    AgentPolicy, DENY_AGENT, ALLOW_AGENT, agent_policy_require_approval,
)
from kiln_server.utils.agent_checks.policy_lookup import (
    AgentPolicyLookup, AgentPolicyError,
)
```

## Component 2: Dump CLI (`dump_annotations.py`)

### Path Normalization

```python
def normalize_endpoint_filename(method: str, path: str) -> str:
    """Convert method + path to a filename.

    Example: ("POST", "/api/projects/{project_id}/tasks")
             -> "post_api_projects_project_id_tasks.json"
    """
    normalized = path.lstrip("/").replace("/", "_").replace("{", "").replace("}", "").lower()
    return f"{method.lower()}_{normalized}.json"
```

### Core Logic

```python
def load_openapi_spec(source: str) -> dict:
    """Load OpenAPI spec from URL or file path."""
    if source.startswith("http://") or source.startswith("https://"):
        import httpx
        response = httpx.get(source)
        response.raise_for_status()
        return response.json()
    else:
        with open(source) as f:
            return json.load(f)

def dump_annotations(source: str, target_folder: str) -> int:
    """Main logic. Returns exit code (0 = success, 2 = unannotated endpoints)."""
    spec = load_openapi_spec(source)
    os.makedirs(target_folder, exist_ok=True)

    unannotated = []
    count = 0

    for path, path_item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if operation is None:
                continue

            count += 1
            policy_data = operation.get("x-agent-policy")

            # Validate policy if present
            if policy_data is not None:
                try:
                    AgentPolicy(**policy_data)
                except (ValueError, ValidationError) as e:
                    print(f"WARNING: Invalid policy on {method.upper()} {path}: {e}")
                    # Still write the file but with null policy
                    policy_data = None

            if policy_data is None:
                unannotated.append(f"{method.upper()} {path}")

            filename = normalize_endpoint_filename(method, path)
            filepath = os.path.join(target_folder, filename)
            with open(filepath, "w") as f:
                json.dump({
                    "method": method,
                    "path": path,
                    "agent_policy": policy_data,
                }, f, indent=2)

    if unannotated:
        print(f"WARNING: {len(unannotated)} unannotated endpoint(s):")
        for ep in unannotated:
            print(f"  {ep}")
        return 2

    print(f"{count} endpoints processed, all annotated.")
    return 0
```

### Entry Point

```python
def main():
    parser = argparse.ArgumentParser(description="Dump API endpoint agent policy annotations")
    parser.add_argument("source", help="OpenAPI spec URL or file path")
    parser.add_argument("target_folder", help="Directory to write annotation JSON files")
    args = parser.parse_args()
    sys.exit(dump_annotations(args.source, args.target_folder))

if __name__ == "__main__":
    main()
```

## Component 3: Policy Lookup (`policy_lookup.py`)

```python
class AgentPolicyError(Exception):
    """Raised when an endpoint has no known policy (fail-safe block)."""

class AgentPolicyLookup:
    def __init__(self, annotations_dir: str | Path):
        self._annotations_dir = Path(annotations_dir)
        self._cache: dict[tuple[str, str], AgentPolicy] | None = None  # (method, path) -> policy

    def _load(self) -> None:
        """Load all annotation files into memory."""
        self._cache = {}
        for filepath in self._annotations_dir.glob("*.json"):
            with open(filepath) as f:
                data = json.load(f)
            method = data["method"].lower()
            path = data["path"]
            policy_data = data.get("agent_policy")
            if policy_data is not None:
                self._cache[(method, path)] = AgentPolicy(**policy_data)
            # If agent_policy is null, we intentionally don't cache it —
            # get_policy will raise AgentPolicyError for missing keys.

    def get_policy(self, method: str, path: str) -> AgentPolicy:
        if self._cache is None:
            self._load()
        assert self._cache is not None  # for type checker
        key = (method.lower(), path)
        if key not in self._cache:
            raise AgentPolicyError(
                f"No agent policy found for {method.upper()} {path}. "
                "Endpoint is blocked by default (fail-safe)."
            )
        return self._cache[key]
```

Key design decisions:
- Lazy load on first `get_policy` call, then cached for instance lifetime.
- Unannotated endpoints (null policy in JSON) are not cached, so they hit the same `AgentPolicyError` path as completely unknown endpoints.
- Lookup uses exact string matching on `(method, path)`. Path parameters are stored with placeholders (`{project_id}`), so callers must pass the template path, not a resolved URL.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Unknown endpoint at runtime | `AgentPolicyError` raised (fail-safe block) |
| Unannotated endpoint at runtime | `AgentPolicyError` raised (same as unknown) |
| Invalid policy in OpenAPI spec | CLI prints warning, writes file with `null` policy |
| CLI can't reach OpenAPI URL | `httpx` raises connection error, CLI exits with traceback |
| CLI given invalid file path | `FileNotFoundError`, CLI exits with traceback |
| Annotations dir doesn't exist | `FileNotFoundError` on first `get_policy` call |
| Malformed JSON in annotations dir | `json.JSONDecodeError` on `_load` |

No custom handling for the last four — standard Python exceptions with tracebacks are appropriate for developer-facing tooling.

## Testing Strategy

All tests use pytest. No external services needed.

### test_policy.py

- **AgentPolicy validation**: Test all valid combinations and all invalid combinations (deny+approval, approval without description, description without approval).
- **Constants**: Verify `DENY_AGENT` and `ALLOW_AGENT` produce correct dict structure.
- **`agent_policy_require_approval`**: Valid description, empty string, whitespace-only string.

### test_dump_annotations.py

- **`normalize_endpoint_filename`**: Various paths including nested, with params, edge cases.
- **`dump_annotations` with all annotated**: Provide a mock OpenAPI spec dict (write to temp file), verify JSON output files and exit code 0.
- **`dump_annotations` with unannotated**: Verify warning output and exit code 2.
- **`dump_annotations` with invalid policy**: Verify warning and null policy in output.
- **URL vs file path loading**: Test `load_openapi_spec` with a file path. URL testing can use a mock/monkeypatch on httpx.
- **`main` entry point**: Test argparse integration with `sys.argv` monkeypatch.

### test_policy_lookup.py

- **Happy path**: Load annotations dir with valid files, look up known endpoint, verify returned `AgentPolicy`.
- **Unknown endpoint**: Look up endpoint not in annotations, verify `AgentPolicyError`.
- **Unannotated endpoint**: Annotation file with `null` policy, verify `AgentPolicyError`.
- **Lazy loading**: Verify files aren't read until first `get_policy` call.
- **Case insensitivity on method**: `GET` vs `get` should both work.

## Dependencies

- `pydantic` — already in use throughout the project
- `httpx` — already a dependency, used for CLI URL fetching
- No new dependencies required
