import json

import pytest
from pydantic import TypeAdapter, ValidationError

from .models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JevAnswer,
    NoulAnswer,
    NoulCriteria,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
    SystemOneResponse,
)

answer_adapter = TypeAdapter(JevAnswer)


def test_question_serialization_omits_unset_and_keeps_none_criteria():
    request = SystemOneRequest(
        state="some content",
        model="jev-latest",
        questions={
            "verdict": ChoiceQuestion(criteria={"pass": None, "fail": "it failed"}),
            "is_spam": NoulQuestion(instructions="Is this spam?"),
        },
    )

    body = request.to_body()

    # Unset optional fields are gone, but a caller's explicit None option description
    # (Jev's "interpret this label by name") survives.
    assert body["questions"]["verdict"] == {
        "type": "choice",
        "criteria": {"pass": None, "fail": "it failed"},
    }
    assert body["questions"]["is_spam"] == {
        "type": "noul",
        "instructions": "Is this spam?",
    }


def test_noul_criteria_serializes_only_provided_ends():
    question = NoulQuestion(
        instructions="Correctness", criteria=NoulCriteria(true="Correctness")
    )
    assert question.model_dump(exclude_none=True)["criteria"] == {"true": "Correctness"}


@pytest.mark.parametrize(
    "levels,valid", [(1, False), (2, True), (10, True), (11, False)]
)
def test_score_question_level_limits(levels: int, valid: bool):
    criteria = [str(level) for level in range(levels)]
    if valid:
        assert len(ScoreQuestion(criteria=criteria).criteria) == levels
    else:
        with pytest.raises(ValidationError):
            ScoreQuestion(criteria=criteria)


@pytest.mark.parametrize(
    "options,valid", [(0, False), (1, True), (255, True), (256, False)]
)
def test_choice_question_option_limits(options: int, valid: bool):
    criteria = {str(option): None for option in range(options)}
    if valid:
        assert len(ChoiceQuestion(criteria=criteria).criteria) == options
    else:
        with pytest.raises(ValidationError):
            ChoiceQuestion(criteria=criteria)


def test_noul_question_requires_instructions():
    with pytest.raises(ValidationError):
        NoulQuestion()  # type: ignore[call-arg]


def test_questions_forbid_unknown_fields():
    with pytest.raises(ValidationError):
        NoulQuestion(instructions="Is this spam?", temperature=0.5)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "raw,expected_type",
    [
        ({"type": "noul", "noul": 0.9, "future_field": 1}, NoulAnswer),
        (
            {
                "type": "choice",
                "choice": "pass",
                "confidence": 0.8,
                "probabilities": {"pass": 0.8, "fail": 0.2},
                "future_field": 1,
            },
            ChoiceAnswer,
        ),
        (
            {
                "type": "score",
                "score": 3.2,
                "confidence": 0.7,
                "legend": {"0": "worst"},
                "probabilities": {"0": 1.0},
                "future_field": 1,
            },
            ScoreAnswer,
        ),
    ],
)
def test_answers_ignore_unknown_fields(raw: dict, expected_type: type):
    answer = answer_adapter.validate_python(raw)
    assert isinstance(answer, expected_type)
    assert not hasattr(answer, "future_field")


def test_response_parses_all_answer_types_and_usage():
    response = SystemOneResponse.model_validate(
        {
            "model": "jev-1.13.0",
            "answers": {
                "is_spam": {"type": "noul", "noul": 0.05},
                "verdict": {
                    "type": "choice",
                    "choice": "pass",
                    "confidence": 0.8,
                    "probabilities": {"pass": 0.8, "fail": 0.2},
                },
                "stars": {
                    "type": "score",
                    "score": 3.4,
                    "confidence": 0.6,
                    "legend": {"0": "1", "1": "2"},
                    "probabilities": {"0": 0.4, "1": 0.6},
                },
            },
            "usage": {"input_tokens": 120, "output_tokens": 12},
            "future_field": "ignored",
        }
    )

    assert response.model == "jev-1.13.0"
    assert isinstance(response.answers["is_spam"], NoulAnswer)
    assert isinstance(response.answers["verdict"], ChoiceAnswer)
    assert isinstance(response.answers["stars"], ScoreAnswer)
    assert response.usage.input_tokens == 120
    assert response.usage.output_tokens == 12


def test_response_usage_defaults_to_empty():
    response = SystemOneResponse.model_validate({"model": "jev-latest", "answers": {}})
    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None


def test_response_rejects_unknown_answer_type():
    with pytest.raises(ValidationError):
        SystemOneResponse.model_validate(
            {"model": "jev-latest", "answers": {"a": {"type": "vibes", "vibes": 1}}}
        )


def test_request_requires_at_least_one_question():
    with pytest.raises(ValidationError):
        SystemOneRequest(state=".", model="jev-latest", questions={})


def test_request_to_body_matches_documented_example():
    request = SystemOneRequest(
        state={"task_instructions": "Judge the answer.", "input": "2 + 2 = 4"},
        model="jev-latest",
        questions={
            "is_correct": NoulQuestion(instructions="Is the answer correct?"),
            "verdict": ChoiceQuestion(
                instructions="Overall verdict",
                criteria={"pass": None, "fail": None},
            ),
            "stars": ScoreQuestion(
                instructions="Rate 1 to 5", criteria=["1", "2", "3", "4", "5"]
            ),
        },
    )

    assert request.to_body() == {
        "state": {"task_instructions": "Judge the answer.", "input": "2 + 2 = 4"},
        "model": "jev-latest",
        "questions": {
            "is_correct": {"type": "noul", "instructions": "Is the answer correct?"},
            "verdict": {
                "type": "choice",
                "instructions": "Overall verdict",
                "criteria": {"pass": None, "fail": None},
            },
            "stars": {
                "type": "score",
                "instructions": "Rate 1 to 5",
                "criteria": ["1", "2", "3", "4", "5"],
            },
        },
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "build_answer",
    [
        pytest.param(lambda v: {"type": "noul", "noul": v}, id="noul"),
        pytest.param(
            lambda v: {
                "type": "choice",
                "choice": "pass",
                "confidence": v,
                "probabilities": {"pass": 1.0},
            },
            id="choice_confidence",
        ),
        pytest.param(
            lambda v: {
                "type": "choice",
                "choice": "pass",
                "confidence": 0.8,
                "probabilities": {"pass": v},
            },
            id="choice_probability",
        ),
        pytest.param(
            lambda v: {
                "type": "score",
                "score": v,
                "confidence": 0.7,
                "legend": {"0": "worst"},
                "probabilities": {"0": 1.0},
            },
            id="score",
        ),
        pytest.param(
            lambda v: {
                "type": "score",
                "score": 1.0,
                "confidence": v,
                "legend": {"0": "worst"},
                "probabilities": {"0": 1.0},
            },
            id="score_confidence",
        ),
        pytest.param(
            lambda v: {
                "type": "score",
                "score": 1.0,
                "confidence": 0.7,
                "legend": {"0": "worst"},
                "probabilities": {"0": v},
            },
            id="score_probability",
        ),
    ],
)
def test_answers_reject_non_finite_numbers(build_answer, value: float):
    with pytest.raises(ValidationError):
        answer_adapter.validate_python(build_answer(value))


def test_response_rejects_bare_nan_token_from_the_wire():
    """`json.loads` accepts the non-standard `NaN` token; the answer models must not,
    so it never reaches the output and the saved run stays valid JSON."""
    payload = json.loads(
        '{"model": "jev-1.13.0", "answers": {"a": {"type": "noul", "noul": NaN}}}'
    )

    with pytest.raises(ValidationError):
        SystemOneResponse.model_validate(payload)
