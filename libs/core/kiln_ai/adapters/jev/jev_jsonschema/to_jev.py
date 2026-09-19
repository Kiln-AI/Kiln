"""JSON Schema -> Jev questions.

`JSONSchema2Jev.convert` turns an object schema into one Jev question per property,
keeping the schema's property order, and reports every property it cannot map in a
single error. The resulting `QuestionSet` is also what `JevResult2JsonSchema` needs to
decode the answers, since it remembers how each property was mapped.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .models import (
    MAX_CHOICE_OPTIONS,
    MAX_SCORE_LEVELS,
    MIN_SCORE_LEVELS,
    ChoiceQuestion,
    JevQuestion,
    JsonContent,
    NoulCriteria,
    NoulQuestion,
    ScoreQuestion,
    SystemOneRequest,
)

ROOT_KEY = "<root>"

COMBINATOR_KEYWORDS = ("anyOf", "oneOf", "allOf", "$ref", "const", "not")


@dataclass(frozen=True)
class PropertyFailure:
    """One schema property that cannot be mapped, and why."""

    key: str
    reason: str


class IncompatibleSchemaError(ValueError):
    """The schema has properties that cannot be expressed as Jev questions.

    Every unmappable property is reported, not just the first.
    """

    def __init__(self, failures: Sequence[PropertyFailure]) -> None:
        self.failures: tuple[PropertyFailure, ...] = tuple(failures)
        details = "\n".join(f"- {f.key}: {f.reason}" for f in self.failures)
        super().__init__(
            f"Schema has properties that cannot be mapped to Jev questions:\n{details}"
        )


class UnexpectedAnswerError(RuntimeError):
    """An answer is missing, has the wrong type for its question, or an out-of-range value."""


class _Unsupported(Exception):
    """Internal: raised while mapping one property, collected into a PropertyFailure."""


class ScoreDecode(str, Enum):
    argmax = "argmax"
    """Use the level with the highest probability; on a tie, the lowest level."""

    expected = "expected"
    """Use the answer's expected value, rounded and clamped to the level range."""


@dataclass(frozen=True)
class MappingOptions:
    """Knobs a consumer can turn. Defaults match the behaviour Kiln uses."""

    noul_threshold: float = 0.5
    max_score_levels: int = MAX_SCORE_LEVELS
    score_decode: ScoreDecode = ScoreDecode.argmax
    instructions_fallback_to_key: bool = True


class MappedKind(str, Enum):
    string_choice = "string_choice"
    integer_choice = "integer_choice"
    boolean_noul = "boolean_noul"
    number_noul = "number_noul"
    score = "score"


@dataclass(frozen=True)
class MappedQuestion:
    """A question plus what is needed to turn its answer back into a schema value."""

    key: str
    kind: MappedKind
    question: NoulQuestion | ChoiceQuestion | ScoreQuestion
    enum_values: tuple[str | int, ...] | None = None
    """Choice kinds only: the schema's enum values, in schema order."""

    minimum: int | None = None
    """Score kind only: the schema value of level 0."""


@dataclass(frozen=True)
class QuestionSet:
    """The mapped questions for one schema, in schema property order."""

    mappings: dict[str, MappedQuestion]

    @property
    def questions(self) -> dict[str, JevQuestion]:
        return {key: mapping.question for key, mapping in self.mappings.items()}

    def request(self, state: JsonContent, model: str) -> SystemOneRequest:
        return SystemOneRequest(state=state, model=model, questions=self.questions)


def _non_blank_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _as_number(value: Any) -> float | None:
    """The value as a float, or None if it is not a number. Booleans are not numbers,
    even though `True == 1` in Python."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _as_integer(value: Any) -> int | None:
    """The value as an int, accepting integral floats such as `5.0`."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


class JSONSchema2Jev:
    def __init__(self, options: MappingOptions = MappingOptions()) -> None:
        self._options = options

    def convert(self, schema: Mapping[str, Any]) -> QuestionSet:
        """Map an object schema's properties onto Jev questions.

        Raises:
            IncompatibleSchemaError: listing every property that cannot be mapped.
        """
        if schema.get("type") not in (None, "object") or not isinstance(
            schema.get("properties"), Mapping
        ):
            raise IncompatibleSchemaError(
                [PropertyFailure(ROOT_KEY, "schema must be an object with properties")]
            )

        properties: Mapping[str, Any] = schema["properties"]
        if not properties:
            raise IncompatibleSchemaError(
                [PropertyFailure(ROOT_KEY, "schema has no properties")]
            )

        mappings: dict[str, MappedQuestion] = {}
        failures: list[PropertyFailure] = []
        for key, prop in properties.items():
            try:
                mappings[key] = self._map_property(key, prop)
            except _Unsupported as err:
                failures.append(PropertyFailure(key, str(err)))

        if failures:
            raise IncompatibleSchemaError(failures)
        return QuestionSet(mappings)

    def _instructions(self, key: str, prop: Mapping[str, Any]) -> str | None:
        return (
            _non_blank_string(prop.get("description"))
            or _non_blank_string(prop.get("title"))
            or (key if self._options.instructions_fallback_to_key else None)
        )

    def _map_property(self, key: str, prop: Any) -> MappedQuestion:
        if not isinstance(prop, Mapping):
            raise _Unsupported("property definition must be an object")

        for keyword in COMBINATOR_KEYWORDS:
            if keyword in prop:
                raise _Unsupported(f"uses '{keyword}', which is not supported")

        if "enum" in prop:
            return self._map_enum(key, prop)

        instructions = self._instructions(key, prop)
        prop_type = prop.get("type")

        if prop_type == "boolean":
            if instructions is None:
                raise _Unsupported("boolean needs a description")
            return MappedQuestion(
                key=key,
                kind=MappedKind.boolean_noul,
                question=NoulQuestion(instructions=instructions),
            )

        if prop_type == "number":
            return self._map_number(key, prop, instructions)

        if prop_type == "integer":
            return self._map_integer(key, prop, instructions)

        if isinstance(prop_type, list):
            raise _Unsupported("multiple types are not supported")

        if prop_type is None:
            raise _Unsupported("no type or enum")
        raise _Unsupported(f"type '{prop_type}' is not supported")

    def _map_enum(self, key: str, prop: Mapping[str, Any]) -> MappedQuestion:
        values = prop.get("enum")
        if not isinstance(values, list):
            raise _Unsupported("enum must be a list of values")
        if not values:
            raise _Unsupported("enum has no values")

        declared_type = prop.get("type")
        if all(isinstance(value, str) for value in values) and declared_type in (
            None,
            "string",
        ):
            kind = MappedKind.string_choice
        elif all(
            isinstance(value, int) and not isinstance(value, bool) for value in values
        ) and declared_type in (None, "integer"):
            kind = MappedKind.integer_choice
        else:
            raise _Unsupported(
                "enum values must be all strings or all integers and match the declared type"
            )

        labels = [str(value) for value in values]
        if len(set(labels)) != len(labels):
            raise _Unsupported("enum has duplicate values")
        if len(labels) > MAX_CHOICE_OPTIONS:
            raise _Unsupported(
                f"enum has {len(labels)} values; Jev choice supports at most {MAX_CHOICE_OPTIONS}"
            )

        return MappedQuestion(
            key=key,
            kind=kind,
            question=ChoiceQuestion(
                instructions=self._instructions(key, prop),
                criteria={label: None for label in labels},
            ),
            enum_values=tuple(values),
        )

    def _map_number(
        self, key: str, prop: Mapping[str, Any], instructions: str | None
    ) -> MappedQuestion:
        minimum = _as_number(prop.get("minimum"))
        maximum = _as_number(prop.get("maximum"))
        if minimum != 0.0 or maximum != 1.0:
            raise _Unsupported(
                "number is only supported with minimum 0 and maximum 1 (mapped to a probability)"
            )
        if instructions is None:
            raise _Unsupported("number needs a description")

        # Criteria frame the probability as a degree of the description rather than the
        # answer to a yes/no question.
        return MappedQuestion(
            key=key,
            kind=MappedKind.number_noul,
            question=NoulQuestion(
                instructions=instructions,
                criteria=NoulCriteria(
                    true=instructions, false=f"inverse of {instructions}"
                ),
            ),
        )

    def _map_integer(
        self, key: str, prop: Mapping[str, Any], instructions: str | None
    ) -> MappedQuestion:
        minimum = _as_integer(prop.get("minimum"))
        maximum = _as_integer(prop.get("maximum"))
        if minimum is None or maximum is None:
            raise _Unsupported(
                "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)"
            )

        levels = maximum - minimum + 1
        if levels < MIN_SCORE_LEVELS:
            raise _Unsupported(
                f"integer range must span at least {MIN_SCORE_LEVELS} values"
            )
        # The option can only lower the cap; the API's own limit still applies.
        max_levels = min(self._options.max_score_levels, MAX_SCORE_LEVELS)
        if levels > max_levels:
            raise _Unsupported(
                f"integer range spans {levels} values; Jev score supports at most {max_levels}"
            )

        return MappedQuestion(
            key=key,
            kind=MappedKind.score,
            question=ScoreQuestion(
                instructions=instructions,
                criteria=[str(value) for value in range(minimum, maximum + 1)],
            ),
            minimum=minimum,
        )
