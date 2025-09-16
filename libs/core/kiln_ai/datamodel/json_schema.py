import json
import re
from typing import Annotated, Dict

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


def _check_json_schema(v: str) -> str:
    """Internal validation function for JSON schema strings.

    Args:
        v: String containing a JSON schema definition

    Returns:
        The input string if valid

    Raises:
        ValueError: If the schema is invalid
    """
    schema_from_json_str(v)
    return v


def validate_schema(instance: Dict, schema_str: str) -> None:
    """Validate a dictionary against a JSON schema.

    Args:
        instance: Dictionary to validate
        schema_str: JSON schema string to validate against

    Raises:
        jsonschema.exceptions.ValidationError: If validation fails
    """
    schema = schema_from_json_str(schema_str)
    v = jsonschema.Draft202012Validator(schema)
    v.validate(instance)


def validate_schema_with_value_error(
    instance: Dict, schema_str: str, error_prefix: str | None = None
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
        validate_schema(instance, schema_str)
    except jsonschema.exceptions.ValidationError as e:
        msg = f"The error from the schema check was: {e.message}. The JSON was: \n```json\n{instance}\n```"
        if error_prefix:
            msg = f"{error_prefix} {msg}"

        raise ValueError(msg) from e


def schema_from_json_str(v: str) -> Dict:
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

        validate_schema_dict(parsed)
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {v}\n {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error parsing JSON schema: {v}\n {e}")


def validate_schema_dict(v: Dict):
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
        # Top level arrays are valid JSON schemas, but we don't want to allow them here as they often cause issues
        if "type" not in v or v["type"] != "object" or "properties" not in v:
            raise ValueError(f"JSON schema must be an object with properties: {v}")
    except jsonschema.exceptions.SchemaError as e:
        raise ValueError(f"Invalid JSON schema: {v} \n{e}")
    except Exception as e:
        raise ValueError(f"Unexpected error validating dict JSON schema: {v}\n {e}")


def string_to_json_key(s: str) -> str:
    """Convert a string to a valid JSON key."""
    return re.sub(r"[^a-z0-9_]", "", s.strip().lower().replace(" ", "_"))
