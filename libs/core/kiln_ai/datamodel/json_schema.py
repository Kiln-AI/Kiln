import json
import re
from copy import deepcopy
from typing import Annotated, Any, Dict

import jsonschema
import jsonschema.exceptions
import jsonschema.validators
from pydantic import AfterValidator

JsonObjectSchema = Annotated[
    str,
    AfterValidator(lambda v: _check_json_schema(v)),
]
"""A pydantic type that validates strings containing JSON schema definitions.
Must be a valid JSON schema object with 'type': 'object' and 'properties' defined.
"""

JsonSchema = Annotated[
    str,
    AfterValidator(lambda v: _check_json_schema(v, require_object=False)),
]
"""A pydantic type that validates strings containing JSON schema definitions.
Must be a valid JSON schema, unlike above does not need to be a object schema.
"""


def _check_json_schema(v: str, require_object: bool = True) -> str:
    """Internal validation function for JSON schema strings.

    Args:
        v: String containing a JSON schema definition

    Returns:
        The input string if valid

    Raises:
        ValueError: If the schema is invalid
    """
    schema_from_json_str(v, require_object=require_object)
    return v


def validate_schema(
    instance: Any, schema_str: str, require_object: bool = True
) -> None:
    """Validate an instance against a JSON schema.

    Args:
        instance: Instance to validate
        schema_str: JSON schema string to validate against

    Raises:
        jsonschema.exceptions.ValidationError: If validation fails
    """
    schema = schema_from_json_str(schema_str, require_object=require_object)
    v = jsonschema.Draft202012Validator(schema)
    v.validate(instance)


def validate_schema_with_value_error(
    instance: Any,
    schema_str: str,
    error_prefix: str | None = None,
    require_object: bool = True,
) -> None:
    """Validate a dictionary against a JSON schema and raise a ValueError if the schema is invalid.

    Args:
        instance: Dictionary to validate
        schema_str: JSON schema string to validate against
        error_prefix: Error message prefix to include in the ValueError

    Raises:
        ValueError: If the instance does not match the schema
    """
    try:
        validate_schema(instance, schema_str, require_object=require_object)
    except jsonschema.exceptions.ValidationError as e:
        msg = f"The error from the schema check was: {e.message}. The JSON was: \n```json\n{instance}\n```"
        if error_prefix:
            msg = f"{error_prefix} {msg}"

        raise ValueError(msg) from e


def schema_from_json_str(v: str, require_object: bool = True) -> Dict:
    """Parse and validate a JSON schema string.

    Args:
        v: String containing a JSON schema definition

    Returns:
        Dict containing the parsed JSON schema

    Raises:
        ValueError: If the input is not a valid JSON schema object with required properties
    """
    try:
        parsed = json.loads(v)
        if not isinstance(parsed, dict):
            raise ValueError(f"JSON schema must be a dict, not {type(parsed)}")

        validate_schema_dict(parsed, require_object=require_object)
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {v}\n {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error parsing JSON schema: {v}\n {e}")


def validate_schema_dict(v: Dict, require_object: bool = True):
    """Parse and validate a JSON schema dictionary.

    Args:
        v: Dictionary containing a JSON schema definition

    Returns:
        Dict containing the parsed JSON schema

    Raises:
        ValueError: If the input is not a valid JSON schema object with required properties
    """
    try:
        jsonschema.Draft202012Validator.check_schema(v)

        if require_object and (
            "type" not in v or v["type"] != "object" or "properties" not in v
        ):
            raise ValueError(f"JSON schema must be an object with properties: {v}")
    except jsonschema.exceptions.SchemaError as e:
        raise ValueError(f"Invalid JSON schema: {v} \n{e}")
    except Exception as e:
        raise ValueError(f"Unexpected error validating dict JSON schema: {v}\n {e}")


def string_to_json_key(s: str) -> str:
    """Convert a string to a valid JSON key."""
    return re.sub(r"[^a-z0-9_]", "", s.strip().lower().replace(" ", "_"))


def single_string_field_name(schema: Dict) -> str | None:
    """
    Return the field name if schema has exactly one string property, otherwise None.

    i.e. {"properties": {"message": {"type": "string"}}} returns "message".
    """
    properties = schema.get("properties", {})
    # Must have exactly one property
    if not isinstance(properties, dict) or len(properties) != 1:
        return None
    # Get the single property name and schema
    field_name, field_schema = next(iter(properties.items()))
    # Return the field name only if it's a string type
    if isinstance(field_schema, dict) and field_schema.get("type") == "string":
        return field_name
    return None


def close_object_schemas(schema: Dict, strict: bool = False) -> Dict:
    """Return a deep-copied schema with object nodes closed by default.

    Any schema node with 'type == "object"' gets 'additionalProperties: false'
    if it is not already set. This normalization is recursive and walks nested
    schema structures such as 'properties', 'items', '$defs', and composed
    schemas like 'anyOf'/'oneOf'/'allOf'. Existing explicit
    'additionalProperties' values are preserved.

    When strict=True, also sets 'required' to list all property keys on every
    object node with 'properties'. This is needed for OpenAI's strict
    structured output mode, which does not support optional properties.
    """

    def _normalize(node: Any) -> Any:
        if isinstance(node, list):
            return [_normalize(item) for item in node]

        if not isinstance(node, dict):
            return node

        normalized = deepcopy(node)

        for key in (
            "properties",
            "$defs",
            "definitions",
            "patternProperties",
            "dependentSchemas",
        ):
            if key in normalized and isinstance(normalized[key], dict):
                normalized[key] = {
                    child_key: _normalize(child_value)
                    for child_key, child_value in normalized[key].items()
                }

        for key in ("items", "additionalProperties", "not", "if", "then", "else"):
            if key in normalized:
                normalized[key] = _normalize(normalized[key])

        for key in ("prefixItems", "allOf", "anyOf", "oneOf"):
            if key in normalized and isinstance(normalized[key], list):
                normalized[key] = [_normalize(item) for item in normalized[key]]

        if (
            normalized.get("type") == "object"
            and "additionalProperties" not in normalized
        ):
            normalized["additionalProperties"] = False

        if (
            strict
            and normalized.get("type") == "object"
            and isinstance(normalized.get("properties"), dict)
        ):
            normalized["required"] = list(normalized["properties"].keys())

        return normalized

    return _normalize(schema)
