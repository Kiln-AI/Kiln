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
    Reference,
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)

_COMPONENT_REF_PREFIX = "#/components/schemas/"
_COMPONENT_PARAM_PREFIX = "#/components/parameters/"

# Sidecar file recording which API version the annotations describe. Consumers
# compare it against the version of the client they are talking to, and skip
# payload validation when the client is newer than the annotations. Named with
# a leading underscore so readers that glob the folder for endpoints skip it.
MANIFEST_FILENAME = "_manifest.json"


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

    def promote_to_def(name: str) -> None:
        """Resolve a component schema into ``deferred_defs`` under its own name.

        Used for references that must stay as references in the output rather
        than being inlined at the use site: cycle back-edges, and discriminator
        mapping targets (a mapping value is a ref *string*, so it has nowhere
        to inline into).
        """
        if deferred_defs.get(name):
            return
        if name in resolving:
            # Mid-resolution: the recursion that owns it deposits the body.
            deferred_defs.setdefault(name, {})
            return
        if name not in components_schemas:
            raise _SchemaResolutionError(
                f"$ref {_COMPONENT_REF_PREFIX + name!r} not found in components.schemas"
            )
        deferred_defs.setdefault(name, {})
        resolving.add(name)
        try:
            deferred_defs[name] = recurse(components_schemas[name])
        finally:
            resolving.discard(name)

    def rewrite_discriminator(discriminator: dict) -> dict:
        """Point a discriminator's mapping at $defs instead of components.

        OpenAPI holds mapping targets as bare ref strings, which the normal
        ``$ref`` walk never sees. Left alone they dangle, because
        components.schemas does not travel with the annotation file.
        """
        mapping = discriminator.get("mapping")
        if not isinstance(mapping, dict):
            return {key: recurse(value) for key, value in discriminator.items()}

        rewritten: dict[str, Any] = {}
        for key, target in mapping.items():
            name = _ref_name(target) if isinstance(target, str) else None
            if name is None:
                rewritten[key] = target
                continue
            promote_to_def(name)
            rewritten[key] = f"#/$defs/{name}"

        return {
            key: (rewritten if key == "mapping" else recurse(value))
            for key, value in discriminator.items()
        }

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
            if deferred_defs.get(name):
                # Already resolved under $defs (cycle or discriminator target).
                # Point at it rather than inlining a second copy.
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

        # Resolve the discriminator first, before walking the sibling keys.
        # It promotes its mapping targets into $defs, and doing that up front
        # lets the sibling oneOf/anyOf branches point at those defs instead of
        # inlining a second copy of each one.
        raw_discriminator = node.get("discriminator")
        discriminator = (
            rewrite_discriminator(raw_discriminator)
            if isinstance(raw_discriminator, dict)
            else None
        )

        return {
            key: (
                discriminator
                if key == "discriminator" and discriminator is not None
                else recurse(value)
            )
            for key, value in node.items()
        }

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


def _resolve_parameter_ref(
    raw: dict,
    components_parameters: dict,
    method: str,
    path: str,
) -> dict | None:
    """Follow a parameter ``$ref`` chain to the parameter object it names.

    Returns the parameter dict unchanged when it holds no ``$ref``, and None
    when the chain cannot be followed. Resolving these matters for override
    order: an operation-level ``$ref`` parameter must still displace the
    path-level parameter of the same name, which needs the name.
    """
    seen: set[str] = set()
    while "$ref" in raw:
        ref = raw["$ref"]
        if not isinstance(ref, str) or not ref.startswith(_COMPONENT_PARAM_PREFIX):
            logger.warning(
                f"Unsupported parameter $ref {ref!r} on {method.upper()} {path}; "
                "skipping parameter"
            )
            return None
        name = ref[len(_COMPONENT_PARAM_PREFIX) :]
        if name in seen:
            logger.warning(
                f"Cyclic parameter $ref {ref!r} on {method.upper()} {path}; "
                "skipping parameter"
            )
            return None
        seen.add(name)
        target = components_parameters.get(name)
        if not isinstance(target, dict):
            logger.warning(
                f"Parameter $ref {ref!r} not found in components.parameters on "
                f"{method.upper()} {path}; skipping parameter"
            )
            return None
        raw = target
    return raw


def _extract_parameters(
    raw_operation: dict,
    raw_path_item: dict,
    components_schemas: dict,
    components_parameters: dict,
    method: str,
    path: str,
) -> dict[str, dict[str, dict]]:
    """Extract path/query parameter schemas, keyed by name within each group.

    Each raw parameter dict is validated through the pydantic model to read
    its name and location, but the raw dict supplies the schema so the key
    order survives verbatim (a model_dump round-trip would reorder it).
    """
    result: dict[str, dict[str, dict]] = {"path": {}, "query": {}}

    raw_params: list[Any] = list(raw_path_item.get("parameters") or []) + list(
        raw_operation.get("parameters") or []
    )

    # Operation-level parameters override path-item ones with the same (name, in).
    merged: dict[tuple[str, ParameterLocation], dict] = {}
    for entry in raw_params:
        if not isinstance(entry, dict):
            continue
        raw = _resolve_parameter_ref(entry, components_parameters, method, path)
        if raw is None:
            continue
        try:
            typed = Parameter.model_validate(raw)
        except ValidationError as e:
            logger.warning(
                f"Invalid parameter on {method.upper()} {path}: {e}; skipping parameter"
            )
            continue
        if typed.param_in not in _SUPPORTED_LOCATIONS:
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


def dump_annotations(source: str, target_folder: str, api_version: str) -> int:
    """Main logic. Returns exit code (0 = success, 2 = unannotated endpoints).

    ``api_version`` is recorded in the manifest and must be the version of the
    *client application* whose API this spec describes. It is required, and
    deliberately not defaulted to the spec's own ``info.version``: that field
    carries the ``kiln-server`` package version, which is a different number
    from the desktop app version consumers compare against.
    """
    spec_dict = load_openapi_spec(source)
    parsed = OpenAPI.model_validate(spec_dict)
    os.makedirs(target_folder, exist_ok=True)

    components_schemas: dict = {}
    components_parameters: dict = {}
    raw_components = spec_dict.get("components")
    if isinstance(raw_components, dict):
        raw_schemas = raw_components.get("schemas")
        if isinstance(raw_schemas, dict):
            components_schemas = raw_schemas
        raw_parameters = raw_components.get("parameters")
        if isinstance(raw_parameters, dict):
            components_parameters = raw_parameters

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
                    raw_operation,
                    raw_path_item,
                    components_schemas,
                    components_parameters,
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

    manifest_path = os.path.join(target_folder, MANIFEST_FILENAME)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "api_version": api_version,
                "endpoint_count": count,
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
    parser.add_argument(
        "--api-version",
        required=True,
        help=(
            "Version of the client application this spec describes, recorded "
            "in the manifest (e.g. the Kiln desktop app version)"
        ),
    )
    args = parser.parse_args()
    sys.exit(dump_annotations(args.source, args.target_folder, args.api_version))


if __name__ == "__main__":
    main()
