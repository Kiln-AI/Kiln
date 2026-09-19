from typing import Any

import pytest

from .models import ChoiceQuestion, NoulQuestion, ScoreQuestion
from .to_jev import (
    IncompatibleSchemaError,
    JSONSchema2Jev,
    MappedKind,
    MappingOptions,
)


def object_schema(**properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties}


def map_one(prop: dict[str, Any], options: MappingOptions | None = None):
    """Convert a schema with a single property named `field` and return its mapping."""
    converter = JSONSchema2Jev(options) if options else JSONSchema2Jev()
    return converter.convert(object_schema(field=prop)).mappings["field"]


def failure_reason(prop: dict[str, Any], options: MappingOptions | None = None) -> str:
    with pytest.raises(IncompatibleSchemaError) as exc_info:
        map_one(prop, options)
    assert len(exc_info.value.failures) == 1
    assert exc_info.value.failures[0].key == "field"
    return exc_info.value.failures[0].reason


@pytest.mark.parametrize("declared_type", [None, "string"])
def test_string_enum(declared_type: str | None):
    prop: dict[str, Any] = {"enum": ["pass", "fail", "critical"]}
    if declared_type:
        prop["type"] = declared_type

    mapping = map_one(prop)

    assert mapping.kind == MappedKind.string_choice
    assert mapping.enum_values == ("pass", "fail", "critical")
    assert isinstance(mapping.question, ChoiceQuestion)
    # Order preserved, bare labels.
    assert list(mapping.question.criteria.items()) == [
        ("pass", None),
        ("fail", None),
        ("critical", None),
    ]


@pytest.mark.parametrize("declared_type", [None, "integer"])
def test_integer_enum_uses_string_labels(declared_type: str | None):
    prop: dict[str, Any] = {"enum": [1, 2, 3]}
    if declared_type:
        prop["type"] = declared_type

    mapping = map_one(prop)

    assert mapping.kind == MappedKind.integer_choice
    assert mapping.enum_values == (1, 2, 3)
    assert isinstance(mapping.question, ChoiceQuestion)
    assert list(mapping.question.criteria.keys()) == ["1", "2", "3"]


@pytest.mark.parametrize(
    "prop,expected_reason",
    [
        ({"enum": []}, "enum has no values"),
        ({"enum": "pass"}, "enum must be a list of values"),
        (
            {"enum": [True, False]},
            "enum values must be all strings or all integers and match the declared type",
        ),
        (
            {"enum": ["pass", 1]},
            "enum values must be all strings or all integers and match the declared type",
        ),
        (
            {"enum": [["pass"]]},
            "enum values must be all strings or all integers and match the declared type",
        ),
        (
            {"enum": ["pass", "fail"], "type": "integer"},
            "enum values must be all strings or all integers and match the declared type",
        ),
        (
            {"enum": [1, 2], "type": "string"},
            "enum values must be all strings or all integers and match the declared type",
        ),
        ({"enum": ["pass", "pass"]}, "enum has duplicate values"),
        ({"enum": [1, 1]}, "enum has duplicate values"),
    ],
)
def test_enum_rejected(prop: dict[str, Any], expected_reason: str):
    assert failure_reason(prop) == expected_reason


def test_enum_option_limit():
    assert map_one({"enum": [str(i) for i in range(255)]}).kind == (
        MappedKind.string_choice
    )
    assert (
        failure_reason({"enum": [str(i) for i in range(256)]})
        == "enum has 256 values; Jev choice supports at most 255"
    )


@pytest.mark.parametrize(
    "prop,expected_instructions",
    [
        (
            {"type": "boolean", "description": "Is it spam?", "title": "Spam"},
            "Is it spam?",
        ),
        ({"type": "boolean", "title": "Spam"}, "Spam"),
        ({"type": "boolean"}, "field"),
        ({"type": "boolean", "description": "   "}, "field"),
    ],
)
def test_boolean_instructions_fallback(
    prop: dict[str, Any], expected_instructions: str
):
    mapping = map_one(prop)

    assert mapping.kind == MappedKind.boolean_noul
    assert isinstance(mapping.question, NoulQuestion)
    assert mapping.question.instructions == expected_instructions
    assert mapping.question.criteria is None


def test_boolean_without_any_instructions_rejected():
    options = MappingOptions(instructions_fallback_to_key=False)
    assert failure_reason({"type": "boolean"}, options) == "boolean needs a description"
    assert map_one({"type": "boolean", "title": "Spam"}, options).kind == (
        MappedKind.boolean_noul
    )


@pytest.mark.parametrize(
    "bounds", [{"minimum": 0, "maximum": 1}, {"minimum": 0.0, "maximum": 1.0}]
)
def test_number_probability_criteria(bounds: dict[str, Any]):
    mapping = map_one({"type": "number", "description": "Correctness", **bounds})

    assert mapping.kind == MappedKind.number_noul
    assert isinstance(mapping.question, NoulQuestion)
    assert mapping.question.instructions == "Correctness"
    assert mapping.question.criteria is not None
    assert mapping.question.criteria.true == "Correctness"
    assert mapping.question.criteria.false == "inverse of Correctness"


@pytest.mark.parametrize(
    "prop",
    [
        {"type": "number"},
        {"type": "number", "minimum": 0},
        {"type": "number", "maximum": 1},
        {"type": "number", "minimum": 1, "maximum": 5},
        {"type": "number", "minimum": 0, "maximum": 100},
        {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
        {"type": "number", "minimum": False, "maximum": True},
    ],
)
def test_number_rejected(prop: dict[str, Any]):
    assert failure_reason({"description": "Correctness", **prop}) == (
        "number is only supported with minimum 0 and maximum 1 (mapped to a probability)"
    )


def test_number_without_any_instructions_rejected():
    assert (
        failure_reason(
            {"type": "number", "minimum": 0, "maximum": 1},
            MappingOptions(instructions_fallback_to_key=False),
        )
        == "number needs a description"
    )


@pytest.mark.parametrize(
    "bounds", [{"minimum": 1, "maximum": 5}, {"minimum": 1.0, "maximum": 5.0}]
)
def test_integer_score_levels(bounds: dict[str, Any]):
    mapping = map_one({"type": "integer", "description": "1 to 5", **bounds})

    assert mapping.kind == MappedKind.score
    assert mapping.minimum == 1
    assert isinstance(mapping.question, ScoreQuestion)
    assert mapping.question.instructions == "1 to 5"
    assert mapping.question.criteria == ["1", "2", "3", "4", "5"]


def test_integer_score_negative_minimum():
    mapping = map_one({"type": "integer", "minimum": -1, "maximum": 1})
    assert mapping.minimum == -1
    assert isinstance(mapping.question, ScoreQuestion)
    assert mapping.question.criteria == ["-1", "0", "1"]


@pytest.mark.parametrize(
    "prop,expected_reason",
    [
        (
            {"type": "integer"},
            "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)",
        ),
        (
            {"type": "integer", "minimum": 1},
            "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)",
        ),
        (
            {"type": "integer", "exclusiveMinimum": 0, "exclusiveMaximum": 6},
            "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)",
        ),
        (
            {"type": "integer", "minimum": 1.5, "maximum": 5},
            "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)",
        ),
        (
            {"type": "integer", "minimum": True, "maximum": 5},
            "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)",
        ),
        (
            {"type": "integer", "minimum": 3, "maximum": 3},
            "integer range must span at least 2 values",
        ),
        (
            {"type": "integer", "minimum": 5, "maximum": 1},
            "integer range must span at least 2 values",
        ),
        (
            {"type": "integer", "minimum": 0, "maximum": 10},
            "integer range spans 11 values; Jev score supports at most 10",
        ),
    ],
)
def test_integer_rejected(prop: dict[str, Any], expected_reason: str):
    assert failure_reason(prop) == expected_reason


def test_integer_ten_levels_accepted():
    mapping = map_one({"type": "integer", "minimum": 1, "maximum": 10})
    assert isinstance(mapping.question, ScoreQuestion)
    assert len(mapping.question.criteria) == 10


def test_max_score_levels_option_lowers_the_cap():
    options = MappingOptions(max_score_levels=5)
    assert map_one({"type": "integer", "minimum": 1, "maximum": 5}, options).kind == (
        MappedKind.score
    )
    assert (
        failure_reason({"type": "integer", "minimum": 1, "maximum": 6}, options)
        == "integer range spans 6 values; Jev score supports at most 5"
    )


def test_max_score_levels_option_cannot_exceed_the_api_limit():
    assert (
        failure_reason(
            {"type": "integer", "minimum": 1, "maximum": 20},
            MappingOptions(max_score_levels=20),
        )
        == "integer range spans 20 values; Jev score supports at most 10"
    )


@pytest.mark.parametrize(
    "prop,expected_reason",
    [
        ({"type": "string"}, "type 'string' is not supported"),
        (
            {"type": "array", "items": {"type": "string"}},
            "type 'array' is not supported",
        ),
        ({"type": "object", "properties": {}}, "type 'object' is not supported"),
        ({"type": "null"}, "type 'null' is not supported"),
        ({"type": ["integer", "null"]}, "multiple types are not supported"),
        ({"description": "no type here"}, "no type or enum"),
        ({}, "no type or enum"),
        ("not-a-schema", "property definition must be an object"),
    ],
)
def test_unsupported_types(prop: Any, expected_reason: str):
    assert failure_reason(prop) == expected_reason


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("anyOf", [{"type": "string"}]),
        ("oneOf", [{"type": "string"}]),
        ("allOf", [{"type": "string"}]),
        ("$ref", "#/$defs/Other"),
        ("const", "fixed"),
        ("not", {"type": "string"}),
    ],
)
def test_combinators_rejected(keyword: str, value: Any):
    # Rejected even when the property also looks mappable on its own.
    assert failure_reason({"type": "boolean", keyword: value}) == (
        f"uses '{keyword}', which is not supported"
    )


@pytest.mark.parametrize(
    "schema,expected_reason",
    [
        ({"type": "string"}, "schema must be an object with properties"),
        ({"type": "object"}, "schema must be an object with properties"),
        (
            {"type": "object", "properties": []},
            "schema must be an object with properties",
        ),
        ({"type": "object", "properties": {}}, "schema has no properties"),
    ],
)
def test_root_schema_rejected(schema: dict[str, Any], expected_reason: str):
    with pytest.raises(IncompatibleSchemaError) as exc_info:
        JSONSchema2Jev().convert(schema)

    assert [(f.key, f.reason) for f in exc_info.value.failures] == [
        ("<root>", expected_reason)
    ]


def test_root_type_may_be_omitted():
    question_set = JSONSchema2Jev().convert({"properties": {"a": {"type": "boolean"}}})
    assert list(question_set.mappings.keys()) == ["a"]


def test_all_failures_reported_in_schema_order():
    schema = object_schema(
        good={"type": "boolean"},
        bad_string={"type": "string"},
        bad_enum={"enum": []},
        bad_integer={"type": "integer"},
    )

    with pytest.raises(IncompatibleSchemaError) as exc_info:
        JSONSchema2Jev().convert(schema)

    assert [f.key for f in exc_info.value.failures] == [
        "bad_string",
        "bad_enum",
        "bad_integer",
    ]
    assert str(exc_info.value) == (
        "Schema has properties that cannot be mapped to Jev questions:\n"
        "- bad_string: type 'string' is not supported\n"
        "- bad_enum: enum has no values\n"
        "- bad_integer: integer needs integer 'minimum' and 'maximum' "
        "(exclusive bounds are not supported)"
    )


def test_incompatible_schema_error_is_a_value_error():
    assert issubclass(IncompatibleSchemaError, ValueError)


def test_question_set_preserves_property_order_and_builds_a_request():
    schema = object_schema(
        verdict={"enum": ["pass", "fail"]},
        stars={"type": "integer", "minimum": 1, "maximum": 5},
        is_spam={"type": "boolean"},
    )

    question_set = JSONSchema2Jev().convert(schema)

    assert list(question_set.mappings.keys()) == ["verdict", "stars", "is_spam"]
    assert [question.type for question in question_set.questions.values()] == [
        "choice",
        "score",
        "noul",
    ]

    body = question_set.request(state={"input": "hi"}, model="jev-latest").to_body()
    assert body["state"] == {"input": "hi"}
    assert body["model"] == "jev-latest"
    assert list(body["questions"].keys()) == ["verdict", "stars", "is_spam"]
    assert body["questions"]["verdict"]["criteria"] == {"pass": None, "fail": None}
