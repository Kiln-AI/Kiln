"""Convert between JSON Schema and TypeSafe Jev's question/answer format.

A self-contained module: pydantic is its only dependency, it imports nothing from Kiln,
and its error messages are neutral so a consumer can present them as-is. It also owns
the System One wire models, so nothing else is needed to build a request or parse a
response.

    question_set = JSONSchema2Jev().convert(schema)
    response = post(question_set.request(state, model).to_body())
    decoded = JevResult2JsonSchema().convert(question_set, response["answers"])
"""

from .from_jev import DecodedResult, JevResult2JsonSchema
from .models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JevAnswer,
    JevQuestion,
    JsonContent,
    NoulAnswer,
    NoulCriteria,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
    SystemOneResponse,
    SystemOneUsage,
)
from .to_jev import (
    ROOT_KEY,
    IncompatibleSchemaError,
    JSONSchema2Jev,
    MappedKind,
    MappedQuestion,
    MappingOptions,
    PropertyFailure,
    QuestionSet,
    ScoreDecode,
    UnexpectedAnswerError,
)

__all__ = [
    "ROOT_KEY",
    "ChoiceAnswer",
    "ChoiceQuestion",
    "DecodedResult",
    "IncompatibleSchemaError",
    "JSONSchema2Jev",
    "JevAnswer",
    "JevQuestion",
    "JevResult2JsonSchema",
    "JsonContent",
    "MappedKind",
    "MappedQuestion",
    "MappingOptions",
    "NoulAnswer",
    "NoulCriteria",
    "NoulQuestion",
    "PropertyFailure",
    "QuestionSet",
    "ScoreAnswer",
    "ScoreDecode",
    "ScoreQuestion",
    "SystemOneRequest",
    "SystemOneResponse",
    "SystemOneUsage",
    "UnexpectedAnswerError",
]
