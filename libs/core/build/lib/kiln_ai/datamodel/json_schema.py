import json
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
        ValueError: If the schema is invalid
    """
    schema = schema_from_json_str(schema_str)
    v = jsonschema.Draft202012Validator(schema)
    return v.validate(instance)


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
        jsonschema.Draft202012Validator.check_schema(parsed)
        if not isinstance(parsed, dict):
            raise ValueError(f"JSON schema must be a dict, not {type(parsed)}")
        if (
            "type" not in parsed
            or parsed["type"] != "object"
            or "properties" not in parsed
        ):
            raise ValueError(f"JSON schema must be an object with properties: {v}")
        return parsed
    except jsonschema.exceptions.SchemaError as e:
        raise ValueError(f"Invalid JSON schema: {v} \n{e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {v}\n {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error parsing JSON schema: {v}\n {e}")