"""Live smoke tests for TypeSafe AI's Jev models.

Every other test in this project fakes the HTTP boundary, so the rest of the suite only
shows that Kiln agrees with itself about the System One wire contract. These tests are the
only place that contract meets the real API: one structured task run through `JevAdapter`
covering every property shape `jev_jsonschema` maps, one V2 LLM Judge with a Jev judge, and
one deliberately bad key to pin down the authentication failure the client claims to map.

So they assert on the shape of what comes back rather than on the calls not raising. The
decode step does much of that work by itself — `JevResult2JsonSchema` raises if an answer
has the wrong type for its question, a label the schema cannot decode, or a score
probability keyed by anything but a level index — and the assertions below cover what it
tolerates: which keys a distribution carries, whether it sums to one, and which properties
carry a confidence.

What they still cannot falsify, so nobody reads more into a green run than it earns: the
`noul` probability pair and its absent confidence are synthesized by `from_jev.py` rather
than read off the wire, so their keys, their sum and the `None` confidence hold whatever
Jev sends (only a `noul` outside 0 to 1 would show, as a negative "false"); a score
question's probability keys are re-keyed from level indices the decoder has already
range-checked, so only the choice properties can catch a drifted wire label; and nothing
checks the response's `model` echo.

They are in their own file so they can be run without pulling in any other paid test:

    uv run python3 -m pytest -n0 -v --runpaid \\
        libs/core/kiln_ai/adapters/jev/test_jev_paid_smoke.py
"""

import json
import os
from typing import Any

import httpx
import pytest

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.eval.v2_eval_llm_judge import LlmJudgeEval
from kiln_ai.adapters.jev.jev_client import (
    JEV_BASE_URL,
    JEV_TIMEOUT_SECONDS,
    JevApiError,
    JevClient,
)
from kiln_ai.adapters.jev.jev_jsonschema import NoulQuestion, SystemOneRequest
from kiln_ai.adapters.model_adapters.jev_adapter import JevAdapter
from kiln_ai.adapters.provider_tools import kiln_model_provider_from
from kiln_ai.adapters.pytest_prerelease_whitelist import PRERELEASE_JEV_MODELS
from kiln_ai.datamodel import Project, Task, TaskOutputRatingType
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    LlmJudgeProperties,
)
from kiln_ai.datamodel.json_schema import validate_schema
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

MODELS_PATH = "/v1/models"

# Jev returns a probability per value, so each distribution should sum to one. The window
# around that is deliberately loose: it is here to catch something that is not a
# distribution at all (percentages from 0 to 100, or 1.0 per key), and the lower bound
# leaves room for a distribution that truncates a negligible tail.
PROBABILITY_SUM_TOLERANCE = 0.05

# One property per row of the functional spec's schema-to-question table, so a single call
# exercises every mapping the adapter can make: a string enum, a bounded integer, an
# integer enum, a boolean, and a number from 0 to 1.
TRIAGE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["spam", "not_spam"],
            "description": "Is this message spam?",
        },
        "severity": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "description": "How harmful is this message, from 1 (harmless) to 5 (very harmful)?",
        },
        "urgency": {
            "type": "integer",
            "enum": [1, 2, 3],
            "description": "How urgently should a person look at this message? 1 is least urgent, 3 is most urgent.",
        },
        "mentions_money": {
            "type": "boolean",
            "description": "Does this message mention money or a payment?",
        },
        "spam_likelihood": {
            # A 0-to-1 number's description becomes the true criterion and "inverse of" it
            # the false one, so it reads as a degree rather than a question.
            "description": "the message is spam",
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
    },
    "required": [
        "verdict",
        "severity",
        "urgency",
        "mentions_money",
        "spam_likelihood",
    ],
}

# The probability keys each property's distribution can carry, in terms of the schema's own
# values. Booleans and 0-to-1 numbers are both answered by a `noul` question, whose
# probability pair is always "true"/"false".
TRIAGE_PROBABILITY_KEYS: dict[str, set[str]] = {
    "verdict": {"spam", "not_spam"},
    "severity": {"1", "2", "3", "4", "5"},
    "urgency": {"1", "2", "3"},
    "mentions_money": {"true", "false"},
    "spam_likelihood": {"true", "false"},
}

# `noul` answers carry no confidence, so these two decode to None while the rest are floats.
TRIAGE_NOUL_PROPERTIES = {"mentions_money", "spam_likelihood"}

TRIAGE_INPUT = (
    "URGENT!!! You have WON a $1,000,000 lottery prize. To claim your winnings, wire a "
    "$50 processing fee to account 4419-2288 within 24 hours. Reply STOP to opt out."
)

JUDGE_SCORES = [
    EvalOutputScore(
        name="Accuracy",
        instruction="Is the answer factually accurate?",
        type=TaskOutputRatingType.pass_fail,
    ),
    EvalOutputScore(
        name="Safety",
        instruction="Is the answer free of harmful content?",
        type=TaskOutputRatingType.pass_fail_critical,
    ),
    EvalOutputScore(
        name="Overall Rating",
        instruction="Rate the answer overall",
        type=TaskOutputRatingType.five_star,
    ),
]

JUDGE_SCORE_KEYS = {"accuracy", "safety", "overall_rating"}

JUDGE_PROBABILITY_KEYS: dict[str, set[str]] = {
    "accuracy": {"pass", "fail"},
    "safety": {"pass", "fail", "critical"},
    "overall_rating": {"1", "2", "3", "4", "5"},
}


@pytest.fixture
def typesafe_api_key() -> str:
    key = os.getenv("TYPESAFE_API_KEY", "")
    if not key:
        pytest.skip(
            "TYPESAFE_API_KEY not set. These tests call TypeSafe AI's live API; set the "
            "key in your environment or .env to run them."
        )
    return key


async def _live_model_ids(api_key: str) -> list[str]:
    try:
        async with httpx.AsyncClient(
            base_url=JEV_BASE_URL, timeout=JEV_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(
                MODELS_PATH,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as err:
        raise AssertionError(
            f"Could not reach GET {JEV_BASE_URL}{MODELS_PATH} to confirm the Jev model "
            f"id: {type(err).__name__}: {err}. This is the preflight, not the System One "
            "call, so check network and proxy access to the host before reading anything "
            "into it."
        ) from err

    assert response.is_success, (
        f"GET {JEV_BASE_URL}{MODELS_PATH} returned HTTP {response.status_code}. Check "
        f"TYPESAFE_API_KEY. Body: {response.text[:500]}"
    )
    try:
        payload: Any = response.json()
    except ValueError as err:
        raise AssertionError(
            f"GET {JEV_BASE_URL}{MODELS_PATH} returned HTTP {response.status_code} with a "
            f"body that is not JSON: {err}. Body: {response.text[:500]}"
        ) from err
    # TypeSafe's listing is {"models": [{"name", "description", "release_date"}]}, not the
    # OpenAI {"data": [{"id"}]} shape — which is why `typesafe` is in SKIP_PROVIDERS in
    # .agents/scripts/provider_utils.py. Both are accepted so this preflight reports a
    # wrong model id rather than failing on the envelope.
    entries: Any = payload
    if isinstance(payload, dict):
        entries = payload.get("models")
        if entries is None:
            entries = payload.get("data")
    assert isinstance(entries, list) and entries, (
        f"GET {JEV_BASE_URL}{MODELS_PATH} did not return a list of models. "
        f"Body: {response.text[:500]}"
    )
    ids: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            ids.append(entry)
        elif isinstance(entry, dict):
            value = entry.get("name") or entry.get("id")
            if isinstance(value, str):
                ids.append(value)
    assert ids, (
        f"GET {JEV_BASE_URL}{MODELS_PATH} returned models with no name. "
        f"Body: {response.text[:500]}"
    )
    return ids


async def _assert_model_id_is_live(
    model_name: str, provider: str, api_key: str
) -> None:
    """Fail by name if the model entry's `model_id` is not one the API offers.

    `jev-1.13.0` came from SDK research and has never been confirmed against a live
    `GET /v1/models`. Without this, a wrong id surfaces as a rejected System One request,
    which reads like a schema or state problem.
    """
    model_id = kiln_model_provider_from(model_name, provider).model_id
    assert model_id is not None, (
        f"The {model_name} entry in ml_model_list.py has no TypeSafe AI model_id."
    )

    live_ids = await _live_model_ids(api_key)
    assert model_id in live_ids, (
        f"ml_model_list.py maps {model_name} to model_id {model_id!r}, which "
        f"GET {JEV_BASE_URL}{MODELS_PATH} does not offer. It lists: {live_ids}. Fix the "
        "entry's model_id before reading anything into the rest of this run."
    )


def _assert_is_distribution(
    key: str, distribution: dict[str, float], allowed: set[str]
) -> None:
    assert distribution, f"no probabilities came back for {key}"
    assert set(distribution) <= allowed, (
        f"{key} probabilities are keyed {sorted(distribution)}, expected a subset of "
        f"{sorted(allowed)}. The wire labels and the schema's own values have drifted."
    )
    assert all(0.0 <= probability <= 1.0 for probability in distribution.values()), (
        f"{key} has a probability outside 0 to 1: {distribution}"
    )
    total = sum(distribution.values())
    assert 0.9 <= total <= 1.0 + PROBABILITY_SUM_TOLERANCE, (
        f"{key} probabilities sum to {total}, so they are not a distribution over its "
        f"values: {distribution}"
    )


@pytest.mark.paid
@pytest.mark.prerelease
@pytest.mark.parametrize("model_name,provider", PRERELEASE_JEV_MODELS)
async def test_jev_structured_task_run_live(
    tmp_path, typesafe_api_key, model_name, provider
):
    await _assert_model_id_is_live(model_name, provider, typesafe_api_key)

    project = Project(name="Jev Smoke", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(
        name="Message Triage",
        instruction=(
            "Triage an inbound message. Decide whether it is spam, how harmful it is, "
            "and how urgently a person should look at it."
        ),
        parent=project,
        output_json_schema=json.dumps(TRIAGE_OUTPUT_SCHEMA),
    )
    task.save_to_file()

    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=ModelProviderName(provider),
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    assert isinstance(adapter, JevAdapter), (
        f"{model_name} on {provider} routed to {type(adapter).__name__}, not JevAdapter"
    )

    task_run = await adapter.invoke(TRIAGE_INPUT)

    output = json.loads(task_run.output.output)
    assert task.output_json_schema is not None
    validate_schema(output, task.output_json_schema)

    # validate_schema accepts 4.0 where the schema says integer, and True where it says
    # integer, so pin the Python types the decoder is supposed to produce.
    assert isinstance(output["verdict"], str)
    assert isinstance(output["severity"], int) and not isinstance(
        output["severity"], bool
    )
    assert isinstance(output["urgency"], int) and not isinstance(
        output["urgency"], bool
    )
    assert isinstance(output["mentions_money"], bool)
    assert isinstance(output["spam_likelihood"], float)

    # The one place this test judges the answer rather than its shape. The input is
    # unambiguous, so a wrong verdict means the state never reached the model intact, not
    # that Jev disagreed with us.
    assert output["verdict"] == "spam", f"unexpected verdict for obvious spam: {output}"
    assert output["mentions_money"] is True, (
        f"the input wires a $50 fee, so this should be True: {output}"
    )

    intermediate_outputs = task_run.intermediate_outputs or {}
    probabilities = json.loads(intermediate_outputs["jev_probabilities"])
    confidence = json.loads(intermediate_outputs["jev_confidence"])

    assert set(probabilities) == set(TRIAGE_PROBABILITY_KEYS)
    assert set(confidence) == set(TRIAGE_PROBABILITY_KEYS)
    for key, allowed in TRIAGE_PROBABILITY_KEYS.items():
        _assert_is_distribution(key, probabilities[key], allowed)

    for key, value in confidence.items():
        if key in TRIAGE_NOUL_PROPERTIES:
            assert value is None, (
                f"{key} is answered by a noul, which has no confidence"
            )
        else:
            assert isinstance(value, float) and 0.0 <= value <= 1.0, (
                f"{key} confidence is {value!r}, expected a number from 0 to 1"
            )

    # A choice the schema cannot decode would already have raised, but the chosen value
    # also has to be one its distribution covers, or `choice` and `probabilities` are keyed
    # differently on the wire.
    for key in ("verdict", "urgency"):
        assert str(output[key]) in probabilities[key], (
            f"{key} decoded to {output[key]!r}, which is not in {probabilities[key]}"
        )

    assert task_run.trace is not None and len(task_run.trace) == 3
    assert task_run.cumulative_usage is not None
    assert (
        task_run.cumulative_usage.total_tokens is not None
        and task_run.cumulative_usage.total_tokens > 0
    ), (
        "TypeSafe AI reported no token usage. The wire model tolerates that, but every "
        "fake in this project returns it and the run details UI would show nothing."
    )


@pytest.mark.paid
@pytest.mark.prerelease
@pytest.mark.parametrize("model_name,provider", PRERELEASE_JEV_MODELS)
async def test_jev_v2_llm_judge_live(tmp_path, typesafe_api_key, model_name, provider):
    await _assert_model_id_is_live(model_name, provider, typesafe_api_key)

    project = Project(name="Jev Judge Smoke", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(
        name="Geography Quiz",
        instruction="Answer the question.",
        parent=project,
    )
    task.save_to_file()
    eval = Eval(
        name="Answer Quality",
        parent=task,
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id="tag::eval_config_set",
        output_scores=JUDGE_SCORES,
    )
    eval.save_to_file()
    eval_config = EvalConfig(
        name="Jev V2 Judge",
        parent=eval,
        config_type=EvalConfigType.v2,
        properties=LlmJudgeProperties(
            model_name=model_name,
            model_provider=provider,
            prompt_template=(
                "Judge this answer to the question 'What is the capital of France?'.\n\n"
                "<answer>{{ final_message }}</answer>\n\n"
                "<steps>{{ judge_instructions }}</steps>"
            ),
            judge_instructions=["Check the answer names the correct city."],
        ),
    )
    eval_config.save_to_file()

    result = await LlmJudgeEval(eval_config).evaluate(
        EvalTaskInput(final_message="The capital of France is Paris.")
    )

    assert result.skipped_reason is None
    assert set(result.scores) == JUDGE_SCORE_KEYS

    assert result.scores["accuracy"] in (0.0, 1.0)
    assert result.scores["safety"] in (-1.0, 0.0, 1.0)
    overall = result.scores["overall_rating"]
    assert 1.0 <= overall <= 5.0 and overall == int(overall), (
        f"a five_star score has to be a whole number from 1 to 5, got {overall!r}"
    )

    # As in the task run above, the one judgement of substance: an answer this plainly
    # correct and harmless should not score a failure, whatever the numbers around it.
    assert result.scores["accuracy"] == 1.0
    assert result.scores["safety"] == 1.0

    assert result.intermediate_outputs is not None
    probabilities = json.loads(result.intermediate_outputs["jev_probabilities"])
    confidence = json.loads(result.intermediate_outputs["jev_confidence"])

    assert set(probabilities) == JUDGE_SCORE_KEYS
    assert set(confidence) == JUDGE_SCORE_KEYS
    for key, allowed in JUDGE_PROBABILITY_KEYS.items():
        _assert_is_distribution(key, probabilities[key], allowed)

    # Every score in a discrete eval schema is a choice or a score question, so all three
    # carry a confidence.
    for key, value in confidence.items():
        assert isinstance(value, float) and 0.0 <= value <= 1.0, (
            f"{key} confidence is {value!r}, expected a number from 0 to 1"
        )


@pytest.mark.paid
@pytest.mark.prerelease
@pytest.mark.parametrize("model_name,provider", PRERELEASE_JEV_MODELS)
async def test_jev_rejects_a_bad_api_key_live(typesafe_api_key, model_name, provider):
    """The whole of `_message_for_status` is belief: nothing live has ever exercised it.

    This pins down its most-guessed branch, and costs nothing — a rejected key answers no
    questions, so it spends no tokens. It takes the `typesafe_api_key` fixture without
    using the key, because the fixture is what says this machine is set up to call the live
    API at all.
    """
    model_id = kiln_model_provider_from(model_name, provider).model_id
    assert model_id is not None

    client = JevClient(api_key="sk-kiln-deliberately-invalid-key")
    request = SystemOneRequest(
        state="Kiln smoke test. This request is expected to be rejected.",
        model=model_id,
        questions={
            "is_rejected": NoulQuestion(
                instructions="Is this request rejected before it is answered?"
            )
        },
    )

    with pytest.raises(JevApiError) as err:
        await client.system_one(request)

    error = err.value
    assert error.status_code is not None, (
        f"the call never got an HTTP response, so nothing here judges the client's error "
        f"table: {error}"
    )
    assert error.status_code in (401, 403), (
        f"a bad key returned HTTP {error.status_code}, so the client's 401/403 branch is "
        f"not the one that maps an authentication failure. Message: {error}"
    )
    assert "Authentication with TypeSafe AI failed" in str(error), (
        f"a bad key produced {str(error)!r}, not the client's authentication message"
    )
    assert error.retryable is False, (
        "an authentication failure must not be retryable, or the eval runner will retry a "
        "key that will never work"
    )
