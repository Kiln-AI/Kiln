import pytest
from pydantic import BaseModel

from kiln_ai.datamodel.json_schema import (
    JsonObjectSchema,
    schema_from_json_str,
    string_to_json_key,
    validate_schema,
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
    "punchline"
  ]
}
"""


def test_json_schema():
    o = ExampleModel(x_schema=json_joke_schema)
    parsed_schema = schema_from_json_str(o.x_schema)
    assert parsed_schema is not None
    assert parsed_schema["type"] == "object"
    assert parsed_schema["required"] == ["setup", "punchline"]
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
    with pytest.raises(Exception):
        validate_schema(0, json_joke_schema)
    o = {"setup": "asdf", "punchline": "asdf"}
    validate_schema(o, json_joke_schema)
    o = {"setup": "asdf", "punchline": "asdf", "rating": "1"}
    with pytest.raises(Exception):
        validate_schema(o, json_joke_schema)


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
    with pytest.raises(Exception):
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
