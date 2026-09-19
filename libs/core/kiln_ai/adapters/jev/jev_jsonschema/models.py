"""Wire models for TypeSafe AI's System One API (`POST /v1/systemone`).

Pydantic mirrors of the API's own models, so a consumer of this module needs nothing
else to build a request body or parse a response. Questions forbid extra fields to
catch typos at construction time; everything the API sends back ignores unknown
fields so a server-side addition does not break parsing.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JsonContent = str | dict[str, Any] | list[Any]
"""Anything the API accepts where free-form content is allowed: a string, an object, or a list."""

MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10


class NoulCriteria(BaseModel):
    """Optional descriptions of what the true and false ends of a noul mean."""

    model_config = ConfigDict(extra="forbid")

    true: JsonContent | None = None
    false: JsonContent | None = None


class NoulQuestion(BaseModel):
    """A yes/no judgement. The answer is the probability of true."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["noul"] = "noul"
    instructions: JsonContent
    criteria: NoulCriteria | None = None


class ChoiceQuestion(BaseModel):
    """Pick one of the labelled options. A `None` description means "interpret by name"."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["choice"] = "choice"
    instructions: JsonContent | None = None
    criteria: dict[str, JsonContent | None] = Field(
        min_length=1, max_length=MAX_CHOICE_OPTIONS
    )


class ScoreQuestion(BaseModel):
    """An ordered rubric. A criteria entry's position is its level, starting at 0."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["score"] = "score"
    instructions: JsonContent | None = None
    criteria: list[JsonContent] = Field(
        min_length=MIN_SCORE_LEVELS, max_length=MAX_SCORE_LEVELS
    )


JevQuestion = Annotated[
    NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")
]


class NoulAnswer(BaseModel):
    """The probability that the noul is true. Carries no confidence."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["noul"]
    noul: float


class ChoiceAnswer(BaseModel):
    """The highest-probability label, with a probability per label."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["choice"]
    choice: str
    confidence: float
    probabilities: dict[str, float]


class ScoreAnswer(BaseModel):
    """The probability-weighted expected level, with a probability per level.

    `probabilities` and `legend` are keyed by 0-based level index as a string.
    """

    model_config = ConfigDict(extra="ignore")

    type: Literal["score"]
    score: float
    confidence: float
    legend: dict[str, JsonContent]
    probabilities: dict[str, float]


JevAnswer = Annotated[
    NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")
]


class SystemOneRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: JsonContent
    model: str
    questions: dict[str, JevQuestion] = Field(min_length=1)

    def to_body(self) -> dict[str, Any]:
        """The JSON body to POST. Unset optional fields are omitted, matching the API's
        own client; `None` choice-criteria descriptions are dict values, so they survive."""
        return self.model_dump(exclude_none=True)


class SystemOneUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input_tokens: int | None = None
    output_tokens: int | None = None


class SystemOneResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    answers: dict[str, JevAnswer]
    usage: SystemOneUsage = SystemOneUsage()
