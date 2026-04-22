import argparse
import json
import logging
import os
import sys
from typing import Any

import httpx
from kiln_server.utils.agent_checks.policy import AgentPolicy
from pydantic import ValidationError

logger = logging.getLogger(__name__)

_COMPONENT_REF_PREFIX = "#/components/schemas/"


class _SchemaResolutionError(Exception):
    """Raised when a schema cannot be fully resolved (e.g. unknown $ref)."""


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
        response = httpx.get(source)
        response.raise_for_status()
        return response.json()
    else:
        with open(source, encoding="utf-8") as f:
            return json.load(f)


def _ref_name(ref: str) -> str | None:
    """Return the component-schema name for a local $ref, else None."""
    if not isinstance(ref, str) or not ref.startswith(_COMPONENT_REF_PREFIX):
        return None
    return ref[len(_COMPONENT_REF_PREFIX) :]


def _inline_schema(
    schema: Any,
    components_schemas: dict,
) -> tuple[Any, dict[str, dict]]:
    """Inline a JSON Schema dict by resolving $refs against components.schemas.

    Returns (inlined_schema, defs_map). When a $ref cycle is detected, the
    back-edge is rewritten to "#/$defs/<Name>" and the target schema is
    deposited in defs_map (itself inlined with any cyclic back-edges preserved).
    Non-cyclic schemas yield an empty defs_map.

    Raises _SchemaResolutionError on unknown or non-local $refs.
    """
    deferred_defs: dict[str, dict] = {}
    resolving: set[str] = set()

    def recurse(node: Any) -> Any:
        if isinstance(node, list):
            return [recurse(item) for item in node]
        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            ref = node["$ref"]
            name = _ref_name(ref)
            if name is None:
                raise _SchemaResolutionError(f"Unsupported $ref: {ref!r}")
            if name in resolving:
                deferred_defs.setdefault(name, {})
                return {"$ref": f"#/$defs/{name}"}
            if name not in components_schemas:
                raise _SchemaResolutionError(
                    f"$ref {ref!r} not found in components.schemas"
                )
            resolving.add(name)
            try:
                inlined = recurse(components_schemas[name])
            finally:
                resolving.discard(name)
            if name in deferred_defs:
                deferred_defs[name] = inlined
                return {"$ref": f"#/$defs/{name}"}
            return inlined

        return {key: recurse(value) for key, value in node.items()}

    inlined_schema = recurse(schema)
    return inlined_schema, deferred_defs


def _inline_with_defs(schema: Any, components_schemas: dict) -> Any:
    """Inline a schema and merge any $defs needed for cycles into the result."""
    inlined, defs_map = _inline_schema(schema, components_schemas)
    if not defs_map:
        return inlined
    if not isinstance(inlined, dict):
        raise _SchemaResolutionError("Cannot attach $defs to non-object schema root")
    assert "$defs" not in inlined, "Unexpected pre-existing $defs in component schema"
    return {**inlined, "$defs": defs_map}


def _extract_request_body(
    operation: dict,
    components_schemas: dict,
    method: str,
    path: str,
) -> dict | None:
    """Extract inlined JSON request body schema, or None if absent/unusable."""
    request_body = operation.get("requestBody")
    if request_body is None:
        return None
    if "$ref" in request_body:
        logger.warning(
            f"Top-level requestBody $ref not supported on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    content = request_body.get("content")
    if not content:
        logger.warning(
            f"requestBody has no content on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    json_entry = content.get("application/json")
    if json_entry is None:
        logger.warning(
            f"requestBody has no application/json content on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    raw_schema = json_entry.get("schema")
    if raw_schema is None:
        logger.warning(
            f"application/json requestBody has no schema on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    inlined = _inline_with_defs(raw_schema, components_schemas)
    return {
        "required": bool(request_body.get("required", False)),
        "content_type": "application/json",
        "schema": inlined,
    }


def _extract_parameters(
    operation: dict,
    path_item: dict,
    components_schemas: dict,
    method: str,
    path: str,
) -> dict[str, dict[str, dict]]:
    """Extract path/query parameter schemas, keyed by name within each group."""
    result: dict[str, dict[str, dict]] = {"path": {}, "query": {}}

    merged: dict[tuple[str, str], dict] = {}
    for param in path_item.get("parameters", []) or []:
        if not isinstance(param, dict):
            continue
        name = param.get("name")
        location = param.get("in")
        if isinstance(name, str) and isinstance(location, str):
            merged[(name, location)] = param
    for param in operation.get("parameters", []) or []:
        if not isinstance(param, dict):
            continue
        name = param.get("name")
        location = param.get("in")
        if isinstance(name, str) and isinstance(location, str):
            merged[(name, location)] = param

    for (name, location), param in merged.items():
        if location not in ("path", "query"):
            continue
        if "$ref" in param:
            logger.warning(
                f"Parameter $ref not supported on {method.upper()} {path} "
                f"(parameter {name!r}); emitting empty schema"
            )
            result[location][name] = {}
            continue
        raw_schema = param.get("schema")
        if raw_schema is None:
            logger.warning(
                f"Parameter {name!r} ({location}) has no schema on "
                f"{method.upper()} {path}; emitting empty schema"
            )
            result[location][name] = {}
            continue
        result[location][name] = _inline_with_defs(raw_schema, components_schemas)

    return result


def dump_annotations(source: str, target_folder: str) -> int:
    """Main logic. Returns exit code (0 = success, 2 = unannotated endpoints)."""
    spec = load_openapi_spec(source)
    os.makedirs(target_folder, exist_ok=True)

    components_schemas = spec.get("components", {}).get("schemas", {})
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
                    logger.error(f"Invalid policy on {method.upper()} {path}: {e}")
                    policy_data = None

            if policy_data is None:
                unannotated.append(f"{method.upper()} {path}")

            try:
                request_body = _extract_request_body(
                    operation, components_schemas, method, path
                )
            except _SchemaResolutionError as e:
                logger.warning(
                    f"Failed to extract request body on {method.upper()} {path}: {e}"
                )
                request_body = None

            try:
                parameters = _extract_parameters(
                    operation, path_item, components_schemas, method, path
                )
            except _SchemaResolutionError as e:
                logger.warning(
                    f"Failed to extract parameters on {method.upper()} {path}: {e}"
                )
                parameters = {"path": {}, "query": {}}

            filename = normalize_endpoint_filename(method, path)
            filepath = os.path.join(target_folder, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "method": method,
                        "path": path,
                        "agent_policy": policy_data,
                        "request_body": request_body,
                        "parameters": parameters,
                    },
                    f,
                    indent=2,
                )
                f.write("\n")

    if unannotated:
        logger.error(
            f"{len(unannotated)} unannotated endpoint(s): " + ", ".join(unannotated)
        )
        return 2

    logger.info(f"{count} endpoints processed, all annotated.")
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
