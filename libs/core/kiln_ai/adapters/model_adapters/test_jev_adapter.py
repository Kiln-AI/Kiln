import json
import re
from unittest.mock import Mock, patch

import pytest

from kiln_ai import datamodel
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.jev import JevApiError, JevClient
from kiln_ai.adapters.jev.jev_jsonschema import (
    ChoiceAnswer,
    DecodedResult,
    NoulAnswer,
    ScoreAnswer,
    SystemOneRequest,
    SystemOneResponse,
    SystemOneUsage,
)
from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    ModelAdapterId,
    ModelProviderName,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.jev_adapter import (
    ERROR_PREFIX,
    JevAdapter,
    build_jev_state,
)
from kiln_ai.adapters.prompt_builders import PromptGenerators
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import SKILL_TOOL_ID_PREFIX
from kiln_ai.tools import KilnToolInterface

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["pass", "fail"],
            "description": "Did the answer pass?",
        },
        "rating": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "description": "Rate from 1 to 5",
        },
        "priority": {
            "type": "integer",
            "enum": [1, 2, 3],
            "description": "How urgent is it?",
        },
        "is_spam": {"type": "boolean", "description": "Is this spam?"},
        "correctness": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "correctness",
        },
    },
    "required": ["verdict", "rating", "priority", "is_spam", "correctness"],
}

ANSWERS = {
    "verdict": ChoiceAnswer(
        type="choice",
        choice="pass",
        confidence=0.91,
        probabilities={"pass": 0.823456, "fail": 0.176544},
    ),
    "rating": ScoreAnswer(
        type="score",
        score=2.6,
        confidence=0.62,
        legend={"0": "1", "1": "2", "2": "3", "3": "4", "4": "5"},
        probabilities={"0": 0.05, "1": 0.1, "2": 0.15, "3": 0.6, "4": 0.1},
    ),
    "priority": ChoiceAnswer(
        type="choice",
        choice="2",
        confidence=0.5,
        probabilities={"1": 0.2, "2": 0.5, "3": 0.3},
    ),
    "is_spam": NoulAnswer(type="noul", noul=0.7),
    "correctness": NoulAnswer(type="noul", noul=0.123456),
}

EXPECTED_OUTPUT = {
    "verdict": "pass",
    "rating": 4,
    "priority": 2,
    "is_spam": True,
    "correctness": 0.123456,
}


class FakeJevClient(JevClient):
    """Records the requests it is given and replays a canned response or error."""

    def __init__(
        self,
        response: SystemOneResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(api_key="fake-key")
        self._response = response
        self._error = error
        self.requests: list[SystemOneRequest] = []

    async def system_one(self, request: SystemOneRequest) -> SystemOneResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def jev_response(
    answers=None, input_tokens: int | None = 120, output_tokens: int | None = 8
) -> SystemOneResponse:
    return SystemOneResponse(
        model="jev-1.13.0",
        answers=answers if answers is not None else dict(ANSWERS),
        usage=SystemOneUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def task():
    return datamodel.Task(
        name="jev-task",
        instruction="Judge the input.",
        output_json_schema=json.dumps(OUTPUT_SCHEMA),
    )


@pytest.fixture
def run_config():
    return KilnAgentRunConfigProperties(
        model_name="jev_1_13",
        model_provider_name=ModelProviderName.typesafe,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
    )


@pytest.fixture(autouse=True)
def jev_model_provider():
    """Resolve the model entry without depending on the model list, which Phase 6 drops."""
    with patch(
        "kiln_ai.adapters.model_adapters.base_adapter.kiln_model_provider_from"
    ) as mock:
        mock.return_value = KilnModelProvider(
            name=ModelProviderName.typesafe,
            model_id="jev-1.13.0",
            adapter=ModelAdapterId.jev,
            supports_data_gen=False,
            supports_function_calling=False,
            structured_output_mode=StructuredOutputMode.json_schema,
        )
        yield mock


@pytest.fixture
def adapter(task, run_config):
    def build(
        client: JevClient | None = None,
        base_adapter_config: AdapterConfig | None = None,
        task_override: datamodel.Task | None = None,
        run_config_override: KilnAgentRunConfigProperties | None = None,
    ) -> JevAdapter:
        return JevAdapter(
            kiln_task=task_override or task,
            run_config=run_config_override or run_config,
            base_adapter_config=base_adapter_config,
            client=client if client is not None else FakeJevClient(jev_response()),
        )

    return build


async def test_rejects_prior_trace(adapter):
    client = FakeJevClient(jev_response())
    with pytest.raises(
        ValueError,
        match=re.escape(f"{ERROR_PREFIX} Jev only supports single-turn runs."),
    ):
        await adapter(client)._run(
            "hi", [], prior_trace=[{"role": "user", "content": "earlier"}]
        )
    assert client.requests == []


@pytest.mark.parametrize("tool_location", ["run_config", "unmanaged"])
async def test_rejects_tools(adapter, run_config, tool_location):
    base_adapter_config = None
    run_config_override = None
    if tool_location == "run_config":
        run_config_override = run_config.model_copy(
            update={"tools_config": ToolsRunConfig(tools=["kiln_tool::add_numbers"])}
        )
    else:
        base_adapter_config = AdapterConfig(
            unmanaged_tools=[Mock(spec=KilnToolInterface)]
        )

    client = FakeJevClient(jev_response())
    with pytest.raises(
        ValueError,
        match=re.escape(f"{ERROR_PREFIX} Jev does not support tools."),
    ):
        await adapter(
            client,
            base_adapter_config=base_adapter_config,
            run_config_override=run_config_override,
        )._run("hi", [])
    assert client.requests == []


async def test_rejects_skills_with_their_own_message(adapter, run_config):
    """Skills are carried in tools_config, but the UI offers them separately, so the
    message has to name what the user actually selected."""
    client = FakeJevClient(jev_response())
    with pytest.raises(
        ValueError,
        match=re.escape(f"{ERROR_PREFIX} Jev does not support skills,"),
    ):
        await adapter(
            client,
            run_config_override=run_config.model_copy(
                update={
                    "tools_config": ToolsRunConfig(
                        tools=[f"{SKILL_TOOL_ID_PREFIX}skill-id"]
                    )
                }
            ),
        )._run("hi", [])
    assert client.requests == []


async def test_tools_reported_before_skills(adapter, run_config):
    """A config with both reports the tools, which the skills message would not cover."""
    with pytest.raises(
        ValueError,
        match=re.escape(f"{ERROR_PREFIX} Jev does not support tools."),
    ):
        await adapter(
            run_config_override=run_config.model_copy(
                update={
                    "tools_config": ToolsRunConfig(
                        tools=[
                            f"{SKILL_TOOL_ID_PREFIX}skill-id",
                            "kiln_tool::add_numbers",
                        ]
                    )
                }
            ),
        )._run("hi", [])


async def test_rejects_task_without_output_schema(adapter, run_config):
    plaintext_task = datamodel.Task(name="plaintext", instruction="Say hi.")
    client = FakeJevClient(jev_response())
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"{ERROR_PREFIX} Jev only supports tasks with a structured output schema."
        ),
    ):
        await adapter(client, task_override=plaintext_task)._run("hi", [])
    assert client.requests == []


async def test_preflight_checks_run_in_order(adapter, run_config):
    """Every rule is broken at once: the message names the first one."""
    plaintext_task = datamodel.Task(name="plaintext", instruction="Say hi.")
    broken = adapter(
        task_override=plaintext_task,
        run_config_override=run_config.model_copy(
            update={"tools_config": ToolsRunConfig(tools=["kiln_tool::add_numbers"])}
        ),
    )
    with pytest.raises(ValueError, match="single-turn"):
        await broken._run("hi", [], prior_trace=[{"role": "user", "content": "x"}])
    with pytest.raises(ValueError, match="does not support tools"):
        await broken._run("hi", [])


async def test_incompatible_schema_reports_every_property(adapter):
    bad_task = datamodel.Task(
        name="bad",
        instruction="Judge.",
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "A summary"},
                    "tags": {"type": "array", "description": "Tags"},
                    "score": {"type": "integer", "description": "Unbounded"},
                    "verdict": {
                        "type": "string",
                        "enum": ["pass", "fail"],
                        "description": "ok",
                    },
                },
                "required": ["summary", "tags", "score", "verdict"],
            }
        ),
    )
    client = FakeJevClient(jev_response())
    with pytest.raises(ValueError) as err:
        await adapter(client, task_override=bad_task)._run("hi", [])

    message = str(err.value)
    assert message.startswith(
        f"{ERROR_PREFIX} the output schema has properties Jev can't answer:"
    )
    assert "- summary: type 'string' is not supported" in message
    assert "- tags: type 'array' is not supported" in message
    assert "- score: " in message
    assert "verdict" not in message
    assert message.endswith("or a number with minimum 0 and maximum 1.")
    assert client.requests == []


async def test_schema_with_no_properties(adapter):
    empty_task = datamodel.Task(
        name="empty",
        instruction="Judge.",
        output_json_schema=json.dumps({"type": "object", "properties": {}}),
    )
    with pytest.raises(
        ValueError,
        match=re.escape(f"{ERROR_PREFIX} the output schema has no properties."),
    ):
        await adapter(task_override=empty_task)._run("hi", [])


@pytest.mark.parametrize(
    "task_input", ["Is this spam?", {"subject": "hello", "body": "buy now"}]
)
async def test_state_carries_instructions_and_input(adapter, task_input):
    client = FakeJevClient(jev_response())
    await adapter(client)._run(task_input, [])

    state = client.requests[0].state
    assert isinstance(state, dict)
    assert state["input"] == task_input
    assert "Judge the input." in state["task_instructions"]


async def test_state_excludes_json_instructions(adapter, run_config):
    """The questions carry the output shape, so a json_instructions run config still
    must not append JSON formatting instructions to the prompt."""
    client = FakeJevClient(jev_response())
    await adapter(
        client,
        run_config_override=run_config.model_copy(
            update={"structured_output_mode": StructuredOutputMode.json_instructions}
        ),
    )._run("hi", [])

    instructions = client.requests[0].state["task_instructions"]  # type: ignore[index]
    assert "JSON" not in instructions


def test_build_jev_state_passes_input_through():
    assert build_jev_state("instructions", {"a": 1}) == {
        "task_instructions": "instructions",
        "input": {"a": 1},
    }


async def test_prompt_content_reaches_state(task, run_config):
    task.requirements = [
        datamodel.TaskRequirement(
            name="Be fair", instruction="Judge without bias", priority=1
        )
    ]
    client = FakeJevClient(jev_response())
    await JevAdapter(kiln_task=task, run_config=run_config, client=client)._run(
        "hi", []
    )

    assert "Judge without bias" in client.requests[0].state["task_instructions"]  # type: ignore[index]


async def test_thinking_instructions_reach_state(task, run_config):
    """Jev runs no thinking step, but a chain-of-thought prompt generator's instructions
    are content — a legacy LLM-as-Judge config carries its eval steps there and nowhere
    else. Composed as `build_prompt_for_ui` does, so the prompt viewer and what Jev
    receives are the same text."""
    task.thinking_instruction = "First, weigh the evidence on both sides."
    client = FakeJevClient(jev_response())
    adapter_under_test = JevAdapter(
        kiln_task=task,
        run_config=run_config.model_copy(
            update={"prompt_id": PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT}
        ),
        client=client,
    )
    await adapter_under_test._run("hi", [])

    instructions = client.requests[0].state["task_instructions"]  # type: ignore[index]
    assert instructions.endswith(
        "\n\n# Thinking Instructions\n\nFirst, weigh the evidence on both sides."
    )
    assert "Judge the input." in instructions
    # The heading is duplicated from build_prompt_for_ui; this is what keeps Kiln's
    # prompt viewer and the text Jev receives from drifting apart.
    assert adapter_under_test.prompt_builder is not None
    assert instructions == adapter_under_test.prompt_builder.build_prompt_for_ui()


async def test_no_thinking_instructions_without_a_cot_prompt_generator(adapter):
    """A prompt generator with no thinking step must not grow an empty heading."""
    client = FakeJevClient(jev_response())
    await adapter(client)._run("hi", [])

    instructions = client.requests[0].state["task_instructions"]  # type: ignore[index]
    assert "# Thinking Instructions" not in instructions


async def test_request_shape(adapter):
    client = FakeJevClient(jev_response())
    await adapter(client)._run("hi", [])

    request = client.requests[0]
    assert request.model == "jev-1.13.0"
    assert list(request.questions.keys()) == list(OUTPUT_SCHEMA["properties"].keys())
    assert request.questions["verdict"].type == "choice"
    assert request.questions["rating"].type == "score"
    assert request.questions["is_spam"].type == "noul"


async def test_decodes_every_question_kind(adapter):
    run_output, _ = await adapter()._run("hi", [])
    assert run_output.output == EXPECTED_OUTPUT


async def test_trace_shape(adapter):
    client = FakeJevClient(jev_response())
    trace_ref = []
    run_output, _ = await adapter(client)._run({"subject": "hi"}, trace_ref)

    assert run_output.trace is trace_ref
    assert [message["role"] for message in trace_ref] == [
        "system",
        "user",
        "assistant",
    ]
    assert trace_ref[0]["content"] == client.requests[0].state["task_instructions"]
    assert trace_ref[1]["content"] == json.dumps({"subject": "hi"})
    assert json.loads(trace_ref[2]["content"]) == EXPECTED_OUTPUT
    assert trace_ref[2]["usage"].total_tokens == 128


async def test_usage_from_response(adapter):
    _, usage = await adapter()._run("hi", [])

    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.output_tokens == 8
    assert usage.total_tokens == 128
    assert usage.cost is None
    assert usage.total_llm_latency_ms is not None
    assert usage.total_llm_latency_ms >= 0


async def test_usage_without_token_counts(adapter):
    client = FakeJevClient(jev_response(input_tokens=None, output_tokens=None))
    _, usage = await adapter(client)._run("hi", [])

    assert usage is not None
    assert usage.total_tokens is None


async def test_intermediate_outputs(adapter):
    run_output, _ = await adapter()._run("hi", [])

    assert run_output.intermediate_outputs is not None
    probabilities = json.loads(run_output.intermediate_outputs["jev_probabilities"])
    confidence = json.loads(run_output.intermediate_outputs["jev_confidence"])

    assert probabilities["verdict"] == {"pass": 0.8235, "fail": 0.1765}
    # Score probabilities are keyed by the schema value, not Jev's 0-based level.
    assert probabilities["rating"] == {
        "1": 0.05,
        "2": 0.1,
        "3": 0.15,
        "4": 0.6,
        "5": 0.1,
    }
    assert probabilities["correctness"] == {"true": 0.1235, "false": 0.8765}
    assert confidence == {
        "verdict": 0.91,
        "rating": 0.62,
        "priority": 0.5,
        "is_spam": None,
        "correctness": None,
    }


async def test_top_logprobs_ignored(adapter):
    client = FakeJevClient(jev_response())
    run_output, _ = await adapter(
        client, base_adapter_config=AdapterConfig(top_logprobs=10)
    )._run("hi", [])

    assert run_output.output == EXPECTED_OUTPUT
    assert run_output.output_logprobs is None


async def test_missing_model_id_raises(adapter, jev_model_provider):
    jev_model_provider.return_value = KilnModelProvider(
        name=ModelProviderName.typesafe, adapter=ModelAdapterId.jev
    )
    client = FakeJevClient(jev_response())
    with pytest.raises(ValueError, match="no TypeSafe AI model ID"):
        await adapter(client)._run("hi", [])
    assert client.requests == []


async def test_end_to_end_through_invoke(task, run_config):
    client = FakeJevClient(jev_response())
    adapter = JevAdapter(kiln_task=task, run_config=run_config, client=client)

    task_run = await adapter.invoke("Is this spam?")

    assert json.loads(task_run.output.output) == EXPECTED_OUTPUT
    assert task_run.output.source.properties["adapter_name"] == "kiln_jev_adapter"
    assert task_run.trace is not None and len(task_run.trace) == 3
    assert task_run.cumulative_usage is not None
    assert task_run.cumulative_usage.total_tokens == 128
    assert "jev_probabilities" in (task_run.intermediate_outputs or {})


async def test_mapping_bug_rejected_by_base_validation(task, run_config):
    """A decoded value outside the schema must not reach a saved run."""
    adapter = JevAdapter(
        kiln_task=task, run_config=run_config, client=FakeJevClient(jev_response())
    )
    broken = {**EXPECTED_OUTPUT, "verdict": "maybe"}
    with patch(
        "kiln_ai.adapters.model_adapters.jev_adapter.JevResult2JsonSchema"
    ) as mock_decoder:
        mock_decoder.return_value.convert.return_value = DecodedResult(
            output=broken, probabilities={}, confidence={}
        )
        with pytest.raises(KilnRunError) as err:
            await adapter.invoke("Is this spam?")

    assert "requires a specific output schema" in str(err.value)


async def test_api_error_reaches_caller(task, run_config):
    error = JevApiError(
        "TypeSafe AI rate limit exceeded. Wait a moment and try again.",
        status_code=429,
        retryable=True,
    )
    adapter = JevAdapter(
        kiln_task=task, run_config=run_config, client=FakeJevClient(error=error)
    )

    with pytest.raises(KilnRunError) as err:
        await adapter.invoke("Is this spam?")

    assert "rate limit exceeded" in str(err.value)
    assert err.value.original is error


async def test_missing_answer_reports_unexpected_response(adapter):
    answers = dict(ANSWERS)
    del answers["rating"]
    client = FakeJevClient(jev_response(answers=answers))
    with pytest.raises(RuntimeError) as err:
        await adapter(client)._run("hi", [])

    message = str(err.value)
    assert message.startswith("TypeSafe AI returned an unexpected response:")
    assert "rating" in message


async def test_streaming_not_supported(adapter):
    with pytest.raises(NotImplementedError):
        adapter()._create_run_stream("hi")


def test_rejects_non_agent_run_config(task):
    with pytest.raises(ValueError, match="KilnAgentRunConfigProperties"):
        JevAdapter(kiln_task=task, run_config="not-a-run-config")  # type: ignore[arg-type]


async def test_builds_client_from_config_when_none_injected(task, run_config):
    adapter = JevAdapter(kiln_task=task, run_config=run_config)

    with (
        patch("kiln_ai.adapters.model_adapters.jev_adapter.JevClient") as mock_client,
        patch("kiln_ai.adapters.model_adapters.jev_adapter.Config") as mock_config,
        patch(
            "kiln_ai.adapters.provider_tools.get_config_value",
            return_value="key-from-config",
        ),
    ):
        mock_client.return_value = FakeJevClient(jev_response())
        mock_config.shared.return_value.typesafe_api_key = "key-from-config"
        await adapter._run("hi", [])

    mock_client.assert_called_once_with(api_key="key-from-config")


async def test_missing_api_key_raises_the_provider_warning(task, run_config):
    """A user-registry model resolves before the provider key check, so the adapter is
    the only thing standing between an unset key and a Bearer None request."""
    adapter = JevAdapter(kiln_task=task, run_config=run_config)

    with patch("kiln_ai.adapters.provider_tools.get_config_value", return_value=None):
        with pytest.raises(
            ValueError, match="Attempted to use TypeSafe AI without an API key set"
        ):
            await adapter._run("hi", [])
