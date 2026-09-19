from typing import Any

import jsonschema
import pytest

from .from_jev import JevResult2JsonSchema
from .models import ChoiceAnswer, NoulAnswer, NoulQuestion, ScoreAnswer
from .to_jev import (
    JSONSchema2Jev,
    MappedKind,
    MappedQuestion,
    MappingOptions,
    QuestionSet,
    ScoreDecode,
    UnexpectedAnswerError,
)

ALL_KINDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["pass", "fail"], "description": "The verdict"},
        "attempts": {"type": "integer", "enum": [1, 2, 3]},
        "is_spam": {"type": "boolean"},
        "correctness": {"type": "number", "minimum": 0, "maximum": 1},
        "stars": {"type": "integer", "minimum": 1, "maximum": 5},
    },
}


def question_set_for(prop: dict[str, Any]) -> QuestionSet:
    return JSONSchema2Jev().convert({"type": "object", "properties": {"field": prop}})


def decode_one(
    prop: dict[str, Any],
    answer: Any,
    options: MappingOptions | None = None,
):
    decoder = JevResult2JsonSchema(options) if options else JevResult2JsonSchema()
    return decoder.convert(question_set_for(prop), {"field": answer})


def choice_answer(choice: str, probabilities: dict[str, float], confidence=0.8):
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities=probabilities,
    )


def score_answer(score: float, probabilities: dict[str, float], confidence=0.7):
    return ScoreAnswer(
        type="score",
        score=score,
        confidence=confidence,
        legend={key: key for key in probabilities},
        probabilities=probabilities,
    )


def test_string_choice():
    decoded = decode_one(
        {"enum": ["pass", "fail"]},
        choice_answer("fail", {"pass": 0.3, "fail": 0.7}, confidence=0.66),
    )

    assert decoded.output == {"field": "fail"}
    assert decoded.probabilities == {"field": {"pass": 0.3, "fail": 0.7}}
    assert decoded.confidence == {"field": 0.66}


def test_integer_choice_casts_to_int():
    decoded = decode_one(
        {"type": "integer", "enum": [1, 2, 3]},
        choice_answer("2", {"1": 0.2, "2": 0.6, "3": 0.2}),
    )

    assert decoded.output == {"field": 2}
    assert isinstance(decoded.output["field"], int)
    assert decoded.probabilities == {"field": {"1": 0.2, "2": 0.6, "3": 0.2}}


@pytest.mark.parametrize(
    "noul,threshold,expected",
    [
        (0.5, None, True),
        (0.49999, None, False),
        (0.0, None, False),
        (1.0, None, True),
        (0.8, 0.9, False),
        (0.9, 0.9, True),
    ],
)
def test_boolean_noul_threshold(noul: float, threshold: float | None, expected: bool):
    options = MappingOptions(noul_threshold=threshold) if threshold else None
    decoded = decode_one(
        {"type": "boolean"}, NoulAnswer(type="noul", noul=noul), options
    )

    assert decoded.output == {"field": expected}
    assert decoded.probabilities == {"field": {"true": noul, "false": 1 - noul}}
    assert decoded.confidence == {"field": None}


def test_number_noul_returns_the_probability():
    decoded = decode_one(
        {"type": "number", "minimum": 0, "maximum": 1},
        NoulAnswer(type="noul", noul=0.25),
    )

    assert decoded.output == {"field": 0.25}
    assert decoded.probabilities == {"field": {"true": 0.25, "false": 0.75}}
    assert decoded.confidence == {"field": None}


def test_score_argmax_with_minimum_offset():
    decoded = decode_one(
        {"type": "integer", "minimum": 1, "maximum": 5},
        score_answer(3.4, {"0": 0.1, "1": 0.1, "2": 0.5, "3": 0.2, "4": 0.1}),
    )

    # Level 2 is the argmax, and the schema's minimum is 1, so the value is 3.
    assert decoded.output == {"field": 3}
    assert decoded.probabilities == {
        "field": {"1": 0.1, "2": 0.1, "3": 0.5, "4": 0.2, "5": 0.1}
    }
    assert decoded.confidence == {"field": 0.7}


def test_score_argmax_tie_picks_the_lowest_level():
    decoded = decode_one(
        {"type": "integer", "minimum": 1, "maximum": 5},
        score_answer(3.0, {"0": 0.1, "1": 0.4, "2": 0.1, "3": 0.4, "4": 0.0}),
    )
    assert decoded.output == {"field": 2}


@pytest.mark.parametrize(
    "score,expected",
    # round() is half-to-even, so 1.5 and 2.5 both land on level index 2, which is
    # the value 3 at minimum=1.
    [(0.4, 1), (1.6, 3), (-5.0, 1), (99.0, 5), (1.5, 3), (2.5, 3)],
)
def test_score_decode_expected_rounds_and_clamps(score: float, expected: int):
    decoded = decode_one(
        {"type": "integer", "minimum": 1, "maximum": 5},
        score_answer(score, {"0": 0.2, "1": 0.2, "2": 0.2, "3": 0.2, "4": 0.2}),
        MappingOptions(score_decode=ScoreDecode.expected),
    )
    assert decoded.output == {"field": expected}


def test_score_empty_probabilities_falls_back_to_expected():
    decoded = decode_one(
        {"type": "integer", "minimum": 1, "maximum": 5},
        score_answer(2.6, {}),
    )

    assert decoded.output == {"field": 4}
    assert decoded.probabilities == {"field": {}}


def test_raw_dict_answers_accepted():
    decoded = JevResult2JsonSchema().convert(
        question_set_for({"enum": ["pass", "fail"]}),
        {
            "field": {
                "type": "choice",
                "choice": "pass",
                "confidence": 0.9,
                "probabilities": {"pass": 0.9, "fail": 0.1},
            }
        },
    )
    assert decoded.output == {"field": "pass"}


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "vibes", "vibes": 1},
        {"type": "choice", "choice": "pass"},
        "not-a-dict",
    ],
)
def test_invalid_raw_dict_answer_raises(raw: Any):
    with pytest.raises(UnexpectedAnswerError, match="is not a valid Jev answer"):
        decode_one({"enum": ["pass", "fail"]}, raw)


def test_missing_answer_raises():
    with pytest.raises(UnexpectedAnswerError, match="no answer for 'field'"):
        JevResult2JsonSchema().convert(question_set_for({"type": "boolean"}), {})


@pytest.mark.parametrize(
    "prop,answer,expected_type",
    [
        ({"type": "boolean"}, choice_answer("pass", {"pass": 1.0}), "noul"),
        (
            {"type": "number", "minimum": 0, "maximum": 1},
            score_answer(1.0, {"0": 1.0}),
            "noul",
        ),
        ({"enum": ["pass"]}, NoulAnswer(type="noul", noul=0.5), "choice"),
        (
            {"type": "integer", "minimum": 1, "maximum": 5},
            NoulAnswer(type="noul", noul=0.5),
            "score",
        ),
    ],
)
def test_wrong_answer_type_raises(
    prop: dict[str, Any], answer: Any, expected_type: str
):
    with pytest.raises(UnexpectedAnswerError, match=f"expected '{expected_type}'"):
        decode_one(prop, answer)


def test_choice_outside_the_enum_raises():
    with pytest.raises(UnexpectedAnswerError, match="chose 'maybe'"):
        decode_one({"enum": ["pass", "fail"]}, choice_answer("maybe", {"maybe": 1.0}))


@pytest.mark.parametrize("probabilities", [{"5": 1.0}, {"-1": 1.0}])
def test_score_level_out_of_range_raises(probabilities: dict[str, float]):
    with pytest.raises(
        UnexpectedAnswerError, match="outside the question's 0 to 4 range"
    ):
        decode_one(
            {"type": "integer", "minimum": 1, "maximum": 5},
            score_answer(1.0, probabilities),
        )


def test_score_non_numeric_probability_key_raises():
    with pytest.raises(UnexpectedAnswerError, match="expected a level index"):
        decode_one(
            {"type": "integer", "minimum": 1, "maximum": 5},
            score_answer(1.0, {"three": 1.0}),
        )


def test_extra_answers_are_ignored():
    decoded = JevResult2JsonSchema().convert(
        question_set_for({"type": "boolean"}),
        {
            "field": NoulAnswer(type="noul", noul=0.9),
            "not_a_question": NoulAnswer(type="noul", noul=0.1),
        },
    )
    assert decoded.output == {"field": True}


def test_round_trip_validates_against_the_source_schema():
    question_set = JSONSchema2Jev().convert(ALL_KINDS_SCHEMA)

    decoded = JevResult2JsonSchema().convert(
        question_set,
        {
            "verdict": choice_answer("pass", {"pass": 0.7, "fail": 0.3}),
            "attempts": choice_answer("3", {"1": 0.1, "2": 0.2, "3": 0.7}),
            "is_spam": NoulAnswer(type="noul", noul=0.05),
            "correctness": NoulAnswer(type="noul", noul=0.9),
            "stars": score_answer(
                4.2, {"0": 0.0, "1": 0.0, "2": 0.1, "3": 0.6, "4": 0.3}
            ),
        },
    )

    assert decoded.output == {
        "verdict": "pass",
        "attempts": 3,
        "is_spam": False,
        "correctness": 0.9,
        "stars": 4,
    }
    assert decoded.confidence == {
        "verdict": 0.8,
        "attempts": 0.8,
        "is_spam": None,
        "correctness": None,
        "stars": 0.7,
    }
    assert list(decoded.probabilities.keys()) == list(
        ALL_KINDS_SCHEMA["properties"].keys()
    )
    jsonschema.Draft202012Validator(ALL_KINDS_SCHEMA).validate(decoded.output)


def test_probabilities_are_not_rounded():
    decoded = decode_one(
        {"enum": ["pass", "fail"]},
        choice_answer("pass", {"pass": 0.123456789, "fail": 0.876543211}),
    )
    assert decoded.probabilities["field"]["pass"] == 0.123456789


def test_mismatched_hand_built_mapping_raises():
    question_set = QuestionSet(
        {
            "field": MappedQuestion(
                key="field",
                kind=MappedKind.score,
                question=NoulQuestion(instructions="x"),
            )
        }
    )
    with pytest.raises(UnexpectedAnswerError, match="not a score question"):
        JevResult2JsonSchema().convert(question_set, {"field": score_answer(3.0, {})})
