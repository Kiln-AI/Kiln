import argparse
import json
import os
import sys

from kiln_server.utils.agent_checks.policy import AgentPolicy
from pydantic import ValidationError


def normalize_endpoint_filename(method: str, path: str) -> str:
    """Convert method + path to a filename.

    Example: ("POST", "/api/projects/{project_id}/tasks")
             -> "post_api_projects_project_id_tasks.json"
    """
    normalized = (
        path.lstrip("/").replace("/", "_").replace("{", "").replace("}", "").lower()
    )
    return f"{method.lower()}_{normalized}.json"


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

    unannotated: list[str] = []
    count = 0

    for path, path_item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if operation is None:
                continue

            count += 1
            policy_data = operation.get("x-agent-policy")

            if policy_data is not None:
                try:
                    AgentPolicy(**policy_data)
                except (ValueError, ValidationError) as e:
                    print(f"WARNING: Invalid policy on {method.upper()} {path}: {e}")
                    policy_data = None

            if policy_data is None:
                unannotated.append(f"{method.upper()} {path}")

            filename = normalize_endpoint_filename(method, path)
            filepath = os.path.join(target_folder, filename)
            with open(filepath, "w") as f:
                json.dump(
                    {
                        "method": method,
                        "path": path,
                        "agent_policy": policy_data,
                    },
                    f,
                    indent=2,
                )
                f.write("\n")

    if unannotated:
        print(f"WARNING: {len(unannotated)} unannotated endpoint(s):")
        for ep in unannotated:
            print(f"  {ep}")
        return 2

    print(f"{count} endpoints processed, all annotated.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump API endpoint agent policy annotations"
    )
    parser.add_argument("source", help="OpenAPI spec URL or file path")
    parser.add_argument(
        "target_folder", help="Directory to write annotation JSON files"
    )
    args = parser.parse_args()
    sys.exit(dump_annotations(args.source, args.target_folder))


if __name__ == "__main__":
    main()
