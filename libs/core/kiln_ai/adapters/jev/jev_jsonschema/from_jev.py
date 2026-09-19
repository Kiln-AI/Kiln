"""Jev answers -> JSON matching the source schema.

`JevResult2JsonSchema.convert` needs the `QuestionSet` that produced the questions,
because that is what remembers how each schema property was mapped. Probabilities and
confidence come back keyed by schema property, with probability keys in terms of the
schema's own values rather than Jev's internal labels.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter, ValidationError

from .models import (
    ChoiceAnswer,
    JevAnswer,
    NoulAnswer,
    ScoreAnswer,
    ScoreQuestion,
)
from .to_jev import (
    MappedKind,
    MappedQuestion,
    MappingOptions,
    QuestionSet,
    ScoreDecode,
    UnexpectedAnswerError,
)

AnswerModel = NoulAnswer | ChoiceAnswer | ScoreAnswer

_ANSWER_ADAPTER: TypeAdapter[AnswerModel] = TypeAdapter(JevAnswer)

_NOUL_KINDS = (MappedKind.boolean_noul, MappedKind.number_noul)
_CHOICE_KINDS = (MappedKind.string_choice, MappedKind.integer_choice)


@dataclass(frozen=True)
class DecodedResult:
    output: dict[str, Any]
    """The decoded object. Validates against the schema the questions came from."""

    probabilities: dict[str, dict[str, float]]
    """Property -> {output value as a string: probability}. Unrounded."""

    confidence: dict[str, float | None]
    """Property -> Jev's confidence. None for noul kinds, which carry no confidence."""


class JevResult2JsonSchema:
    def __init__(self, options: MappingOptions = MappingOptions()) -> None:
        self._options = options

    def convert(
        self,
        question_set: QuestionSet,
        answers: Mapping[str, JevAnswer | Mapping[str, Any]],
    ) -> DecodedResult:
        """Decode one answer per mapped question. Extra answers are ignored.

        Raises:
            UnexpectedAnswerError: an answer is missing, has the wrong type for its
                question, or holds a value the question cannot produce.
        """
        output: dict[str, Any] = {}
        probabilities: dict[str, dict[str, float]] = {}
        confidence: dict[str, float | None] = {}

        for key, mapping in question_set.mappings.items():
            if key not in answers:
                raise UnexpectedAnswerError(f"no answer for '{key}'")
            answer = self._as_answer_model(key, answers[key])

            if mapping.kind in _NOUL_KINDS:
                if not isinstance(answer, NoulAnswer):
                    raise _wrong_answer_type(key, answer, "noul")
                output[key] = (
                    answer.noul >= self._options.noul_threshold
                    if mapping.kind == MappedKind.boolean_noul
                    else answer.noul
                )
                probabilities[key] = {"true": answer.noul, "false": 1 - answer.noul}
                confidence[key] = None
            elif mapping.kind in _CHOICE_KINDS:
                if not isinstance(answer, ChoiceAnswer):
                    raise _wrong_answer_type(key, answer, "choice")
                output[key] = self._decode_choice(key, mapping, answer)
                probabilities[key] = dict(answer.probabilities)
                confidence[key] = answer.confidence
            else:
                if not isinstance(answer, ScoreAnswer):
                    raise _wrong_answer_type(key, answer, "score")
                minimum = mapping.minimum if mapping.minimum is not None else 0
                level_count = _score_level_count(mapping)
                levels = self._decode_score_probabilities(key, answer, level_count)
                output[key] = minimum + self._decode_score_level(
                    answer, levels, level_count
                )
                probabilities[key] = {
                    str(minimum + level): probability
                    for level, probability in levels.items()
                }
                confidence[key] = answer.confidence

        return DecodedResult(
            output=output, probabilities=probabilities, confidence=confidence
        )

    def _as_answer_model(
        self, key: str, raw: JevAnswer | Mapping[str, Any]
    ) -> AnswerModel:
        if isinstance(raw, (NoulAnswer, ChoiceAnswer, ScoreAnswer)):
            return raw
        try:
            return _ANSWER_ADAPTER.validate_python(raw)
        except ValidationError as err:
            raise UnexpectedAnswerError(
                f"answer for '{key}' is not a valid Jev answer: {_first_validation_message(err)}"
            ) from err

    def _decode_choice(
        self, key: str, mapping: MappedQuestion, answer: ChoiceAnswer
    ) -> str | int:
        values_by_label = {str(value): value for value in mapping.enum_values or ()}
        if answer.choice not in values_by_label:
            raise UnexpectedAnswerError(
                f"answer for '{key}' chose '{answer.choice}', which is not one of the "
                "schema's enum values"
            )
        return values_by_label[answer.choice]

    def _decode_score_probabilities(
        self, key: str, answer: ScoreAnswer, level_count: int
    ) -> dict[int, float]:
        """The answer's probabilities re-keyed by integer level, rejecting anything that
        is not a 0-based level index of this question."""
        levels: dict[int, float] = {}
        for raw_level, probability in answer.probabilities.items():
            try:
                level = int(raw_level)
            except ValueError:
                raise UnexpectedAnswerError(
                    f"answer for '{key}' has probability key '{raw_level}', expected a level index"
                ) from None
            if not 0 <= level < level_count:
                raise UnexpectedAnswerError(
                    f"answer for '{key}' has level {level}, outside the question's "
                    f"0 to {level_count - 1} range"
                )
            levels[level] = probability
        return levels

    def _decode_score_level(
        self, answer: ScoreAnswer, levels: dict[int, float], level_count: int
    ) -> int:
        if levels and self._options.score_decode == ScoreDecode.argmax:
            highest = max(levels.values())
            return min(level for level, p in levels.items() if p == highest)

        # Either the caller asked for the expected value, or there are no probabilities
        # to pick an argmax from and the expected value is all we have.
        return max(0, min(level_count - 1, round(answer.score)))


def _wrong_answer_type(
    key: str, answer: AnswerModel, expected: str
) -> UnexpectedAnswerError:
    return UnexpectedAnswerError(
        f"answer for '{key}' has type '{answer.type}', expected '{expected}'"
    )


def _score_level_count(mapping: MappedQuestion) -> int:
    question = mapping.question
    if not isinstance(question, ScoreQuestion):
        raise UnexpectedAnswerError(
            f"question '{mapping.key}' is mapped as a score but is not a score question"
        )
    return len(question.criteria)


def _first_validation_message(err: ValidationError) -> str:
    errors = err.errors()
    return str(errors[0]["msg"]) if errors else str(err)
