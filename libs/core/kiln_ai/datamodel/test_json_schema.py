import json

import jsonschema
import pytest
from pydantic import BaseModel

from kiln_ai.datamodel.json_schema import (
    JsonObjectSchema,
    _normalize_schema,
    schema_from_json_str,
    schemas_compatible,
    single_string_field_name,
    string_to_json_key,
    validate_schema,
    validate_schema_with_value_error,
)


class ExampleModel(BaseModel):
    x_schema: JsonObjectSchema | None = None


json_joke_schema = """{
  "type": "object",
  "properties": {
    "setup": {
      "description": "The setup of the joke",
      "title": "Setup",
      "type": "string"
    },
    "punchline": {
      "description": "The punchline to the joke",
      "title": "Punchline",
      "type": "string"
    },
    "rating": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "How funny the joke is, from 1 to 10",
      "title": "Rating"
    }
  },
  "required": [
    "setup",
    "punchline",
    "rating"
  ],
  "additionalProperties": false
}
"""


def test_json_schema():
    o = ExampleModel(x_schema=json_joke_schema)
    parsed_schema = schema_from_json_str(o.x_schema)
    assert parsed_schema is not None
    assert parsed_schema["type"] == "object"
    assert parsed_schema["required"] == ["setup", "punchline", "rating"]
    assert parsed_schema["properties"]["setup"]["type"] == "string"
    assert parsed_schema["properties"]["punchline"]["type"] == "string"
    assert parsed_schema["properties"]["rating"] is not None

    # Not json schema
    with pytest.raises(ValueError):
        o = ExampleModel(x_schema="hello")
    with pytest.raises(ValueError):
        o = ExampleModel(x_schema="{'asdf':{}}")
    with pytest.raises(ValueError):
        o = ExampleModel(x_schema="{asdf")


def test_validate_schema_content():
    o = {"setup": "asdf", "punchline": "asdf", "rating": 1}
    validate_schema(o, json_joke_schema)
    o = {"setup": "asdf"}
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_schema(0, json_joke_schema)
    o = {"setup": "asdf", "punchline": "asdf", "rating": None}
    validate_schema(o, json_joke_schema)
    o = {"setup": "asdf", "punchline": "asdf", "rating": "1"}
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_schema(o, json_joke_schema)


def test_validate_schema_content_with_value_error():
    o = {"setup": "asdf", "punchline": "asdf", "rating": 1}
    validate_schema_with_value_error(o, json_joke_schema, "PREFIX")
    o = {"setup": "asdf"}
    with pytest.raises(
        ValueError, match="PREFIX The error from the schema check was: "
    ):
        validate_schema_with_value_error(0, json_joke_schema, "PREFIX")
    o = {"setup": "asdf", "punchline": "asdf", "rating": None}
    validate_schema_with_value_error(o, json_joke_schema, "PREFIX")
    o = {"setup": "asdf", "punchline": "asdf", "rating": "1"}
    with pytest.raises(
        ValueError, match="PREFIX The error from the schema check was: "
    ):
        validate_schema_with_value_error(o, json_joke_schema, "PREFIX")


json_triangle_schema = """{
  "type": "object",
  "properties": {
    "a": {
      "description": "length of side a",
      "title": "A",
      "type": "integer"
    },
    "b": {
      "description": "length of side b",
      "title": "B",
      "type": "integer"
    },
    "c": {
      "description": "length of side c",
      "title": "C",
      "type": "integer"
    }
  },
  "required": [
    "a",
    "b",
    "c"
  ]
}
"""


def test_triangle_schema():
    o = ExampleModel(x_schema=json_joke_schema)
    parsed_schema = schema_from_json_str(o.x_schema)
    assert parsed_schema is not None

    o = ExampleModel(x_schema=json_triangle_schema)
    schema = schema_from_json_str(o.x_schema)

    assert schema is not None
    assert schema["properties"]["a"]["type"] == "integer"
    assert schema["properties"]["b"]["type"] == "integer"
    assert schema["properties"]["c"]["type"] == "integer"
    assert schema["required"] == ["a", "b", "c"]
    validate_schema({"a": 1, "b": 2, "c": 3}, json_triangle_schema)
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_schema({"a": 1, "b": 2, "c": "3"}, json_triangle_schema)


@pytest.mark.parametrize(
    "input_str,expected",
    [
        ("hello world", "hello_world"),
        ("Hello World", "hello_world"),
        ("hello_world", "hello_world"),
        ("HELLO WORLD", "hello_world"),
        ("hello123", "hello123"),
        ("hello-world", "helloworld"),
        ("hello!@#$%^&*()world", "helloworld"),
        ("  hello  world  ", "hello__world"),
        ("hello__world", "hello__world"),
        ("", ""),
        ("!@#$%", ""),
        ("snake_case_string", "snake_case_string"),
        ("camelCaseString", "camelcasestring"),
    ],
)
def test_string_to_json_key(input_str: str, expected: str):
    assert string_to_json_key(input_str) == expected


def test_array_schema_validation():
    array_schema = {
        "type": "array",
        "items": {"type": "integer"},
        "description": "A list of integers",
    }
    value = [1, 2, 3]
    schema_str = json.dumps(array_schema)

    # Arrays not valid by default, must be object (some things reply on this, like tools)
    with pytest.raises(ValueError):
        validate_schema(value, schema_str)

    # Arrays are not valid if we require an object
    with pytest.raises(ValueError):
        validate_schema(value, schema_str, require_object=True)

    # Arrays are valid if we don't require an object
    validate_schema(value, schema_str, require_object=False)


@pytest.mark.parametrize(
    "schema,expected",
    [
        # Returns field name when exactly one string property
        ({"properties": {"message": {"type": "string"}}}, "message"),
        (
            {
                "properties": {
                    "content": {"type": "string", "description": "The content"}
                }
            },
            "content",
        ),
        # Returns None for empty or multiple properties
        ({"properties": {}}, None),
        ({"properties": {"name": {"type": "string"}, "age": {"type": "number"}}}, None),
        # Returns None when single property is not a string
        ({"properties": {"count": {"type": "number"}}}, None),
        ({"properties": {"user": {"type": "object"}}}, None),
        ({"properties": {"items": {"type": "array"}}}, None),
        # Returns None for invalid schemas
        ({}, None),
        ({"properties": "invalid"}, None),
    ],
)
def test_single_string_field_name(schema, expected):
    assert single_string_field_name(schema) == expected


@pytest.mark.parametrize(
    "schema,expected",
    [
        # Removes additionalProperties from dict
        (
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "additionalProperties": False,
            },
            {"type": "object", "properties": {"x": {"type": "string"}}},
        ),
        # Returns dict unchanged if no additionalProperties
        (
            {"type": "object", "properties": {"x": {"type": "string"}}},
            {"type": "object", "properties": {"x": {"type": "string"}}},
        ),
        # Returns non-dict types unchanged
        ("string", "string"),
        # Only removes top-level additionalProperties, not nested
        (
            {
                "type": "object",
                "properties": {
                    "nested": {"type": "object", "additionalProperties": False}
                },
                "additionalProperties": True,
            },
            {
                "type": "object",
                "properties": {
                    "nested": {"type": "object", "additionalProperties": False}
                },
            },
        ),
    ],
)
def test_normalize_schema(schema, expected):
    result = _normalize_schema(schema)
    assert result == expected
    # Ensure it returns a copy, not modifying the original
    if isinstance(schema, dict):
        assert result is not schema


@pytest.mark.parametrize(
    "task_schema, tool_schema, description",
    [
        (
            {"type": "object", "properties": {"name": {"type": "string"}}},
            {"type": "object", "properties": {"name": {"type": "string"}}},
            "identical_schemas",
        ),
        (
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "additionalProperties": True,
            },
            "different_additionalProperties",
        ),
        (
            {"type": "string", "minLength": 1},
            {"type": "string", "minLength": 1},
            "non_object_matching",
        ),
    ],
)
def test_schemas_compatible_true(task_schema, tool_schema, description):
    assert schemas_compatible(task_schema, tool_schema)


@pytest.mark.parametrize(
    "task_schema, tool_schema, description",
    [
        (
            {"type": "object", "properties": {"x": {"type": "string"}}},
            {"type": "string"},
            "different_types",
        ),
        (
            {"type": "object", "properties": {"name": {"type": "string"}}},
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
                "required": ["name", "age"],
            },
            "missing_required_field",
        ),
        (
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "extra": {"type": "string"}},
            },
            {"type": "object", "properties": {"name": {"type": "string"}}},
            "unaccepted_field",
        ),
        (
            {"type": "object", "properties": {"age": {"type": "string"}}},
            {"type": "object", "properties": {"age": {"type": "number"}}},
            "field_type_mismatch",
        ),
        (
            {"type": "number", "minimum": 0},
            {"type": "number", "minimum": 10},
            "non_object_different_constraints",
        ),
    ],
)
def test_schemas_compatible_false(task_schema, tool_schema, description):
    assert not schemas_compatible(task_schema, tool_schema)
