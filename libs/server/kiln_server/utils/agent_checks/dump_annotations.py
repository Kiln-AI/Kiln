import argparse
import json
import logging
import os
import sys
from typing import Any

import httpx
from kiln_server.utils.agent_checks.policy import AgentPolicy
from openapi_pydantic import (
    OpenAPI,
    Operation,
    Parameter,
    ParameterLocation,
    PathItem,
    Reference,
)
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
    operation: Operation,
    raw_operation: dict,
    components_schemas: dict,
    method: str,
    path: str,
) -> dict | None:
    """Extract inlined JSON request body schema, or None if absent/unusable.

    Pydantic models drive structural decisions; the schema payload itself
    comes from the raw spec dict to preserve key ordering verbatim.
    """
    request_body = operation.requestBody
    if request_body is None:
        return None
    if isinstance(request_body, Reference):
        logger.warning(
            f"Top-level requestBody $ref not supported on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    if not request_body.content:
        logger.warning(
            f"requestBody has no content on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    json_entry = request_body.content.get("application/json")
    if json_entry is None:
        logger.warning(
            f"requestBody has no application/json content on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    if json_entry.media_type_schema is None:
        logger.warning(
            f"application/json requestBody has no schema on {method.upper()} {path}; "
            "skipping request body schema"
        )
        return None
    raw_schema = raw_operation["requestBody"]["content"]["application/json"]["schema"]
    inlined = _inline_with_defs(raw_schema, components_schemas)
    return {
        "required": request_body.required,
        "content_type": "application/json",
        "schema": inlined,
    }


_SUPPORTED_LOCATIONS = (ParameterLocation.PATH, ParameterLocation.QUERY)


def _extract_parameters(
    operation: Operation,
    path_item: PathItem,
    raw_operation: dict,
    raw_path_item: dict,
    components_schemas: dict,
    method: str,
    path: str,
) -> dict[str, dict[str, dict]]:
    """Extract path/query parameter schemas, keyed by name within each group.

    Pydantic-parsed Parameter objects are zipped with the raw parameter dicts
    (order-preserved by pydantic) so we can look up schemas without reordering
    their keys via a model_dump round-trip.
    """
    result: dict[str, dict[str, dict]] = {"path": {}, "query": {}}

    typed_params: list[Parameter | Reference] = list(path_item.parameters or []) + list(
        operation.parameters or []
    )
    raw_params: list[Any] = list(raw_path_item.get("parameters") or []) + list(
        raw_operation.get("parameters") or []
    )

    # Operation-level parameters override path-item ones with the same (name, in).
    merged: dict[tuple[str, ParameterLocation], dict] = {}
    for typed, raw in zip(typed_params, raw_params):
        if isinstance(typed, Reference):
            logger.warning(
                f"Parameter $ref not supported on {method.upper()} {path} "
                f"(parameter {typed.ref!r}); skipping"
            )
            continue
        if typed.param_in not in _SUPPORTED_LOCATIONS:
            continue
        if not isinstance(raw, dict):
            continue
        merged[(typed.name, typed.param_in)] = raw

    for (name, param_in), raw in merged.items():
        location = param_in.value
        raw_schema = raw.get("schema")
        if raw_schema is None:
            logger.warning(
                f"Parameter {name!r} ({location}) has no schema on "
                f"{method.upper()} {path}; emitting empty schema"
            )
            result[location][name] = {}
            continue
        result[location][name] = _inline_with_defs(raw_schema, components_schemas)

    return result


_METHODS = ("get", "post", "put", "patch", "delete")


def dump_annotations(source: str, target_folder: str) -> int:
    """Main logic. Returns exit code (0 = success, 2 = unannotated endpoints)."""
    spec_dict = load_openapi_spec(source)
    parsed = OpenAPI.model_validate(spec_dict)
    os.makedirs(target_folder, exist_ok=True)

    components_schemas: dict = {}
    raw_components = spec_dict.get("components")
    if isinstance(raw_components, dict):
        raw_schemas = raw_components.get("schemas")
        if isinstance(raw_schemas, dict):
            components_schemas = raw_schemas

    unannotated: list[str] = []
    count = 0

    raw_paths = spec_dict.get("paths") or {}
    for path, path_item in (parsed.paths or {}).items():
        raw_path_item = raw_paths.get(path) or {}
        for method in _METHODS:
            operation: Operation | None = getattr(path_item, method)
            if operation is None:
                continue
            raw_operation = raw_path_item.get(method) or {}

            count += 1
            policy_data = (operation.model_extra or {}).get("x-agent-policy")

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
                    operation, raw_operation, components_schemas, method, path
                )
            except _SchemaResolutionError as e:
                logger.warning(
                    f"Failed to extract request body on {method.upper()} {path}: {e}"
                )
                request_body = None

            try:
                parameters = _extract_parameters(
                    operation,
                    path_item,
                    raw_operation,
                    raw_path_item,
                    components_schemas,
                    method,
                    path,
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
