"""A Jev judge in Kiln's two LLM judges.

Neither judge is Jev-aware: both build their score schema with
`build_score_schema(allow_float_scores=False)` and pick their adapter through
`adapter_for_task`. These tests hold the two claims that design rests on — that every
shape the eval score schema emits maps onto a Jev question, and that a judge scores end
to end with only the HTTP client faked.
"""

import json
from typing import Any
from unittest.mock import patch

import pytest

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.adapters.eval.v2_eval_llm_judge import LlmJudgeEval
from kiln_ai.adapters.jev import JevApiError, JevClient
from kiln_ai.adapters.jev.jev_jsonschema import (
    ChoiceAnswer,
    ChoiceQuestion,
    JevAnswer,
    JevQuestion,
    JSONSchema2Jev,
    MappedKind,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
    SystemOneResponse,
    SystemOneUsage,
)
from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    ModelAdapterId,
    ModelProviderName,
)
from kiln_ai.adapters.retry_classification import is_retryable_error
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    LlmJudgeProperties,
)

JUDGE_MODEL_NAME = "jev_1_13"

# One score of each rating type build_score_schema can emit, which is the whole surface
# a Jev judge has to answer.
JUDGE_SCORES = [
    EvalOutputScore(
        name="Accuracy",
        instruction="Is the answer accurate?",
        type=TaskOutputRatingType.pass_fail,
    ),
    EvalOutputScore(
        name="Safety",
        instruction="Is the answer safe?",
        type=TaskOutputRatingType.pass_fail_critical,
    ),
    EvalOutputScore(
        name="Overall Rating",
        instruction="Rate the answer overall",
        type=TaskOutputRatingType.five_star,
    ),
]

JUDGE_ANSWERS: dict[str, Any] = {
    "accuracy": "pass",
    "safety": "critical",
    "overall_rating": 4,
}

EXPECTED_SCORES = {"accuracy": 1.0, "safety": -1.0, "overall_rating": 4.0}


def _spread(labels: list[str], target: str, mass: float) -> dict[str, float]:
    rest = (1.0 - mass) / (len(labels) - 1) if len(labels) > 1 else 0.0
    return {label: (mass if label == target else rest) for label in labels}


def _answer_for(question: JevQuestion, desired: Any) -> JevAnswer:
    """A wire answer of the right type for `question` that decodes back to `desired`."""
    if isinstance(question, ChoiceQuestion):
        labels = list(question.criteria.keys())
        target = str(desired)
        assert target in labels, f"{target!r} is not one of {labels}"
        return ChoiceAnswer(
            type="choice",
            choice=target,
            confidence=0.8,
            probabilities=_spread(labels, target, 0.7),
        )
    if isinstance(question, ScoreQuestion):
        criteria = [str(level) for level in question.criteria]
        levels = [str(index) for index in range(len(criteria))]
        target = str(criteria.index(str(desired)))
        probabilities = _spread(levels, target, 0.6)
        return ScoreAnswer(
            type="score",
            score=sum(int(level) * p for level, p in probabilities.items()),
            confidence=0.75,
            legend=dict(zip(levels, criteria)),
            probabilities=probabilities,
        )
    # Unreachable from the eval score schema, which emits only string enums and
    # bounded integers; kept so ScriptedJevClient stays general.
    assert isinstance(question, NoulQuestion)
    return NoulAnswer(type="noul", noul=float(desired))


class ScriptedJevClient(JevClient):
    """Answers whatever questions it is asked, so the real mapping runs in both
    directions: the caller names the output value it wants per property, and the answer
    is built from the question the schema actually produced."""

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(api_key="scripted-key")
        self._values = values
        self.requests: list[SystemOneRequest] = []
        self.error: Exception | None = None
        """Set to make the next call fail instead of answering."""

    async def system_one(self, request: SystemOneRequest) -> SystemOneResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        missing = set(request.questions) - set(self._values)
        assert not missing, f"no scripted answer for {sorted(missing)}"
        return SystemOneResponse(
            model=request.model,
            answers={
                key: _answer_for(question, self._values[key])
                for key, question in request.questions.items()
            },
            usage=SystemOneUsage(input_tokens=210, output_tokens=6),
        )


@pytest.fixture
def judge_task(tmp_path):
    project = Project(name="Jev Judge Project", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(
        name="Joke Generator",
        instruction="Generate a joke, given a topic",
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def judge_eval(judge_task):
    eval = Eval(
        name="Joke Quality Eval",
        parent=judge_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=JUDGE_SCORES,
    )
    eval.save_to_file()
    return eval


@pytest.fixture
def task_run(judge_task):
    run = TaskRun(
        parent=judge_task,
        input="Tell me a chicken joke",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "test_user"}
        ),
        output=TaskOutput(
            output="Why did the chicken cross the road? To get to the other side!"
        ),
    )
    run.save_to_file()
    return run


@pytest.fixture
def scripted_client():
    return ScriptedJevClient(JUDGE_ANSWERS)


@pytest.fixture
def jev_judge(scripted_client):
    """Route a TypeSafe judge to a JevAdapter backed by the scripted client.

    Only the network call and the model-list lookup are replaced — `adapter_for_task`
    does the real routing — so these tests keep working once Phase 6 removes the Jev
    model entry.
    """
    provider = KilnModelProvider(
        name=ModelProviderName.typesafe,
        model_id="jev-1.13.0",
        adapter=ModelAdapterId.jev,
        supports_data_gen=False,
        supports_logprobs=False,
        supports_function_calling=False,
        structured_output_mode=StructuredOutputMode.json_schema,
    )
    with (
        patch(
            "kiln_ai.adapters.model_adapters.jev_adapter._client_from_config",
            return_value=scripted_client,
        ),
        patch(
            "kiln_ai.adapters.adapter_registry.kiln_model_provider_from",
            return_value=provider,
        ),
        patch(
            "kiln_ai.adapters.model_adapters.base_adapter.kiln_model_provider_from",
            return_value=provider,
        ),
    ):
        yield scripted_client


@pytest.fixture
def legacy_eval_config(judge_eval):
    config = EvalConfig(
        name="Jev Judge",
        parent=judge_eval,
        config_type=EvalConfigType.llm_as_judge,
        model_name=JUDGE_MODEL_NAME,
        model_provider=ModelProviderName.typesafe.value,
        properties={
            "eval_steps": [
                "Is the joke funny?",
                "Is the content appropriate for all audiences?",
            ],
            "task_description": "Generate a joke about a topic",
        },
    )
    config.save_to_file()
    return config


def _v2_config(judge_eval, **property_overrides) -> EvalConfig:
    properties = {
        "model_name": JUDGE_MODEL_NAME,
        "model_provider": ModelProviderName.typesafe.value,
        "prompt_template": "Rate this output: {{ final_message }}",
        **property_overrides,
    }
    config = EvalConfig(
        name="Jev V2 Judge",
        parent=judge_eval,
        config_type=EvalConfigType.v2,
        properties=LlmJudgeProperties(**properties),
    )
    config.save_to_file()
    return config


def test_judge_scores_cover_every_discrete_rating_type():
    """The mapping test below is only a contract if JUDGE_SCORES is exhaustive.
    `custom` is excluded: `build_score_schema` skips it, so it emits no property."""
    assert {score.type for score in JUDGE_SCORES} | {
        TaskOutputRatingType.custom
    } == set(TaskOutputRatingType)


def test_eval_score_schema_maps_to_jev_questions(judge_eval):
    """Every shape the discrete eval score schema emits has to be a Jev question, or a
    Jev judge fails at run time on a schema Kiln generated itself."""
    schema = json.loads(
        BaseEval.build_score_schema(judge_eval, allow_float_scores=False)
    )
    question_set = JSONSchema2Jev().convert(schema)

    assert {key: mapping.kind for key, mapping in question_set.mappings.items()} == {
        "accuracy": MappedKind.string_choice,
        "safety": MappedKind.string_choice,
        "overall_rating": MappedKind.score,
    }

    accuracy = question_set.mappings["accuracy"].question
    assert isinstance(accuracy, ChoiceQuestion)
    assert accuracy.criteria == {"pass": None, "fail": None}
    # Label order is part of the promise: it can move Jev's prior.
    assert list(accuracy.criteria) == ["pass", "fail"]

    safety = question_set.mappings["safety"].question
    assert isinstance(safety, ChoiceQuestion)
    assert safety.criteria == {"pass": None, "fail": None, "critical": None}
    assert list(safety.criteria) == ["pass", "fail", "critical"]

    overall = question_set.mappings["overall_rating"]
    assert isinstance(overall.question, ScoreQuestion)
    assert overall.question.criteria == ["1", "2", "3", "4", "5"]
    assert overall.minimum == 1


def test_eval_schema_question_instructions_carry_the_rubric(judge_eval):
    """The scoring instruction and scale sentence live in the property description, which
    is what becomes the question's instructions — no eval-specific handling needed. That
    holds for both question kinds an eval schema produces: the score, and the choice a
    pass/fail score maps to."""
    schema = json.loads(
        BaseEval.build_score_schema(judge_eval, allow_float_scores=False)
    )
    question_set = JSONSchema2Jev().convert(schema)

    overall = question_set.mappings["overall_rating"].question
    assert overall.instructions == schema["properties"]["overall_rating"]["description"]
    assert "Rate the answer overall" in str(overall.instructions)
    assert "an integer from 1 to 5" in str(overall.instructions)

    # A pass/fail score's criteria are the bare labels `pass` / `fail` / `critical`, so a
    # choice question's instructions are the only place its rubric can ride.
    accuracy = question_set.mappings["accuracy"]
    assert accuracy.kind == MappedKind.string_choice
    assert (
        accuracy.question.instructions
        == schema["properties"]["accuracy"]["description"]
    )
    assert "Is the answer accurate?" in str(accuracy.question.instructions)

    safety = question_set.mappings["safety"]
    assert safety.kind == MappedKind.string_choice
    assert safety.question.instructions == schema["properties"]["safety"]["description"]
    assert "Is the answer safe?" in str(safety.question.instructions)


async def test_legacy_llm_as_judge_scores_with_jev(
    jev_judge, legacy_eval_config, task_run
):
    scores, intermediate_outputs = await GEval(legacy_eval_config, None).run_eval(
        task_run
    )

    assert scores == EXPECTED_SCORES
    assert intermediate_outputs is not None
    assert json.loads(intermediate_outputs["jev_probabilities"])["overall_rating"] == {
        "1": 0.1,
        "2": 0.1,
        "3": 0.1,
        "4": 0.6,
        "5": 0.1,
    }
    assert json.loads(intermediate_outputs["jev_confidence"]) == {
        "accuracy": 0.8,
        "safety": 0.8,
        "overall_rating": 0.75,
    }


async def test_legacy_judge_state_drops_the_eval_steps_by_design(
    jev_judge, legacy_eval_config, task_run
):
    """`eval_steps` is a legacy judge config's only required property, and it reaches the
    model only as thinking instructions, which Jev is not sent because it has no thinking
    step. So a legacy Jev judge does not see its own steps.

    Accepted rather than worked around: no UI path creates a legacy judge config any more,
    and the V2 judge is unaffected because its `judge_instructions` render into the prompt
    template. Everything else about the judge prompt still arrives."""
    await GEval(legacy_eval_config, None).run_eval(task_run)

    assert len(jev_judge.requests) == 1
    state = jev_judge.requests[0].state
    assert isinstance(state, dict)
    assert "evaluate a model's performance" in state["task_instructions"]
    assert "Generate a joke about a topic" in state["task_instructions"]
    assert "Is the joke funny?" not in state["task_instructions"]
    assert (
        "Is the content appropriate for all audiences?"
        not in state["task_instructions"]
    )
    assert task_run.output.output in state["input"]
    assert list(jev_judge.requests[0].questions) == list(JUDGE_ANSWERS)


async def test_legacy_judges_differing_only_in_eval_steps_send_identical_bodies(
    jev_judge, judge_eval, task_run
):
    """The other half of the same deliberate trade-off: with the eval steps gone, two
    legacy judge configs that differ only in their steps are the same judge to Jev, so
    comparing them compares nothing. Legacy judge configs are unreachable from the UI, and
    a V2 judge's instructions travel in the prompt template instead."""
    bodies = []
    for steps in (["Is the joke funny?"], ["Reject any joke mentioning animals."]):
        config = EvalConfig(
            name=f"Jev Judge {len(bodies)}",
            parent=judge_eval,
            config_type=EvalConfigType.llm_as_judge,
            model_name=JUDGE_MODEL_NAME,
            model_provider=ModelProviderName.typesafe.value,
            properties={"eval_steps": steps},
        )
        config.save_to_file()
        await GEval(config, None).run_eval(task_run)
        bodies.append(jev_judge.requests[-1].to_body())

    assert bodies[0] == bodies[1]


async def test_v2_llm_judge_scores_with_jev(jev_judge, judge_eval):
    config = _v2_config(
        judge_eval,
        prompt_template=(
            "Rate this output: {{ final_message }}\n<steps>{{ judge_instructions }}</steps>"
        ),
        judge_instructions=["Is the joke funny?"],
    )
    result = await LlmJudgeEval(config).evaluate(
        EvalTaskInput(final_message="Why did the chicken cross the road?")
    )

    assert result.scores == EXPECTED_SCORES
    assert result.skipped_reason is None
    assert result.usage is not None and result.usage.total_tokens == 216
    assert result.intermediate_outputs is not None
    assert "jev_probabilities" in result.intermediate_outputs

    state = jev_judge.requests[0].state
    assert isinstance(state, dict)
    assert "Why did the chicken cross the road?" in state["input"]
    # Unlike the legacy judge's eval_steps, the V2 judge's steps render into the prompt
    # template, which becomes the state input Jev reads.
    assert "Is the joke funny?" in state["input"]


async def test_v2_g_eval_rejected_before_adapter_selection(judge_eval):
    """The V2 judge's `supports_logprobs` guard has to run before the adapter is built,
    or the failure would come from the network.

    The guard only fires for a model that has a built-in entry, which is why the lookup
    is patched here. A Jev model without one -- a user-registry model, or any Jev model
    while the `ml_model_list.py` entry is absent -- is not rejected server-side and fails
    late with "No logprobs found for output"; the model dropdown's `requires_logprobs`
    filter is what keeps it out of reach. See the project backlog.
    """
    config = _v2_config(judge_eval, g_eval=True)
    provider = KilnModelProvider(
        name=ModelProviderName.typesafe,
        model_id="jev-1.13.0",
        adapter=ModelAdapterId.jev,
        supports_logprobs=False,
    )

    with (
        patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.built_in_models_from_provider",
            return_value=provider,
        ),
        patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task"
        ) as mock_adapter_for_task,
    ):
        with pytest.raises(ValueError, match="g_eval=True requires logprobs support"):
            await LlmJudgeEval(config).evaluate(EvalTaskInput(final_message="hi"))

    mock_adapter_for_task.assert_not_called()


async def test_judge_api_error_surfaces_and_is_retryable(
    scripted_client, legacy_eval_config, task_run, jev_judge
):
    """A transient judge failure has to reach the eval runner's classifier intact, since
    the adapter itself never retries."""
    scripted_client.error = JevApiError(
        "TypeSafe AI is currently unavailable. Try again in a moment.",
        status_code=503,
        retryable=True,
    )

    with pytest.raises(Exception) as err:
        await GEval(legacy_eval_config, None).run_eval(task_run)

    assert "TypeSafe AI is currently unavailable" in str(err.value)
    assert is_retryable_error(err.value) is True
