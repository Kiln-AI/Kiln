"""ground_case against the test OpenEnv server, with the model scripted (`conftest.py`)."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import jsonschema
import litellm
import pytest

from kiln_ai.adapters import adapter_registry
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.eval_grounding.agent import (
    NO_SUBMISSION_ERROR,
    ground_case,
    structured_output_mode,
)
from kiln_ai.eval_grounding.conftest import model_reply
from kiln_ai.eval_grounding.models import (
    INPUT_SCHEMA_MISMATCH,
    DropReason,
    EvalContext,
    GroundingCase,
)
from kiln_ai.eval_grounding.prompt import system_prompt
from kiln_ai.eval_grounding.session import TOOLS_CLOSED_MESSAGE, GroundingLimits
from kiln_ai.openenv.session_manager import OpenEnvTransientError

CASE = GroundingCase(
    scenario="A clerk asks to add a note.",
    seed_prompt="Add a note please.",
    synthetic_user_info="<persona>A clerk</persona>\n<goal>Add a note</goal>",
)

EVAL_CONTEXT = EvalContext(
    specification="The agent adds notes when asked.",
    target_task_prompt="Help clerks keep notes.",
)


def result(*, args: Any = '{"limit": 5}', **overrides: Any) -> dict[str, Any]:
    """A grounded result as the model returns it. `args` is a JSON string, as the
    structured output schema asks; pass a dict for the submit_result tool."""
    return {
        "status": "grounded",
        "drop_reason": None,
        "drop_detail": None,
        "seed_prompt": "Add the note 'hi' please.",
        "synthetic_user_info": "<persona>A clerk</persona><goal>Add hi</goal>",
        "reference": {
            "starting_point": "The notebook is empty.",
            "facts": [
                {
                    "text": "The notebook is empty.",
                    "evidence": {
                        "tool": "read_notes",
                        "args": args,
                        "result_excerpt": "[]",
                    },
                }
            ],
            "expected_outcome": "The notebook holds 'hi'.",
        },
        **overrides,
    }


def start(fixture_id: str = "a"):
    return ("start_episode", {"reset_kwargs": {"fixture_id": fixture_id}})


READ_NOTES = ("read_notes", {})


def submit(**fields: Any):
    return ("submit_result", fields)


@pytest.fixture
async def ground(openenv_server, session_manager):
    server_tools = await session_manager.list_tools(openenv_server)

    async def run(case: GroundingCase = CASE, **overrides: Any):
        kwargs: dict[str, Any] = {
            "eval_context": EVAL_CONTEXT,
            "openenv_server": openenv_server,
            "session_manager": session_manager,
            "server_tools": server_tools,
            "model_name": "gpt-4",
            "model_provider": ModelProviderName.openai,
            "target_tools": [],
            "reset_schema": None,
            "time_limit_s": 30,
            **overrides,
        }
        return await ground_case(case, **kwargs)

    return run


@pytest.fixture
def built_adapters():
    """Every adapter ground_case builds, so a test can read what the model is sent."""
    adapters: list[BaseAdapter] = []
    real = adapter_registry.adapter_for_task

    def capture(*args: Any, **kwargs: Any) -> BaseAdapter:
        adapter = real(*args, **kwargs)
        adapters.append(adapter)
        return adapter

    with patch("kiln_ai.eval_grounding.agent.adapter_for_task", side_effect=capture):
        yield adapters


def sent_text(messages: list[Any]) -> str:
    return json.dumps(messages, default=str, ensure_ascii=False)


def _role(message: Any) -> str:
    return message["role"] if isinstance(message, dict) else message.role


class TestStructuredOutput:
    async def test_grounds_with_the_last_reset_not_the_models(
        self, ground, scripted_model, openenv_server, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start("a")),
            model_reply(None, start("b")),
            model_reply(None, READ_NOTES),
            model_reply(json.dumps(result(), ensure_ascii=False)),
        )
        outcome = await ground()

        assert outcome.status == "grounded"
        assert outcome.openenv_reset is not None
        assert outcome.openenv_reset.reset_kwargs == {"fixture_id": "b"}
        assert outcome.openenv_reset.openenv_server_id == openenv_server.id
        assert outcome.reference is not None
        assert outcome.reference.facts[0].evidence.args == {"limit": 5}
        assert outcome.seed_prompt == "Add the note 'hi' please."
        assert [c.tool for c in outcome.call_log] == [
            "start_episode",
            "start_episode",
            "read_notes",
        ]
        assert outcome.usage is not None
        assert outcome.usage.input_tokens == 40
        assert outcome.usage_complete
        await server_is_free()

    async def test_the_model_gets_the_prompt_and_the_case(self, ground, scripted_model):
        scripted_model.script(model_reply(json.dumps(result(), ensure_ascii=False)))
        await ground(system_prompt_text="Ground this case.")
        system, user = scripted_model.sent[0][:2]
        assert system == {"role": "system", "content": "Ground this case."}
        assert (
            "<case_scenario>\nA clerk asks to add a note.\n</case_scenario>"
            in (user["content"])
        )

    async def test_the_thinking_level_reaches_the_model_call(
        self, ground, scripted_model, built_adapters
    ):
        scripted_model.script(model_reply(json.dumps(result(), ensure_ascii=False)))
        scripted_model.script(model_reply(json.dumps(result(), ensure_ascii=False)))
        await ground()
        await ground(thinking_level="high")
        default, chosen = built_adapters
        assert default.run_config.thinking_level is None  # type: ignore[union-attr]
        assert chosen.run_config.thinking_level == "high"  # type: ignore[union-attr]

    async def test_the_schema_the_model_sees_keeps_args(
        self, ground, scripted_model, built_adapters
    ):
        scripted_model.script(model_reply(json.dumps(result(), ensure_ascii=False)))
        await ground()
        [adapter] = built_adapters
        assert adapter.base_adapter_config.automatic_prompt_caching
        assert adapter.run_config.structured_output_mode == (  # type: ignore[union-attr]
            StructuredOutputMode.json_schema
        )
        sent_schema = adapter.json_schema_response_format()[  # type: ignore[attr-defined]
            "response_format"
        ]["json_schema"]["schema"]
        jsonschema.validate(result(), sent_schema)
        tool_names = [d["function"]["name"] for d in await adapter.litellm_tools()]  # type: ignore[attr-defined]
        assert "submit_result" not in tool_names
        assert tool_names[:2] == ["start_episode", "read_state"]

    async def test_unparseable_reply_is_retried_in_the_same_conversation(
        self, ground, scripted_model, server_is_free, built_adapters
    ):
        scripted_model.script(
            model_reply(None, start("a")),
            model_reply("not json at all"),
            model_reply(None, start("b")),
            model_reply(json.dumps(result(), ensure_ascii=False)),
        )
        outcome = await ground()

        assert outcome.status == "grounded"
        assert outcome.openenv_reset is not None
        assert outcome.openenv_reset.reset_kwargs == {"fixture_id": "a"}
        assert outcome.call_log[-1].tool == "start_episode"
        assert outcome.call_log[-1].output == TOOLS_CLOSED_MESSAGE
        # The follow-up runs on the same adapter, so it is cached the same way.
        [adapter] = built_adapters
        assert adapter.base_adapter_config.automatic_prompt_caching
        # The adapter rejected the first run's answer, so its tokens are missing.
        assert not outcome.usage_complete
        assert outcome.usage is not None and outcome.usage.input_tokens == 20
        first_run, follow_up = scripted_model.sent[1], scripted_model.sent[2]
        assert follow_up[:2] == first_run[:2]
        assert [_role(m) for m in follow_up] == [
            *(_role(m) for m in first_run),
            "assistant",
            "user",
        ]
        assert "not json at all" in sent_text(follow_up)
        assert follow_up[-1]["role"] == "user"
        assert "could not be used" in follow_up[-1]["content"]
        await server_is_free()

    async def test_a_reply_off_the_schema_is_retried(self, ground, scripted_model):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps({"status": "grounded"}, ensure_ascii=False)),
            model_reply(json.dumps(result(), ensure_ascii=False)),
        )
        outcome = await ground()
        assert outcome.status == "grounded"
        follow_up = scripted_model.sent[2][-1]["content"]
        assert follow_up.startswith("Your last reply could not be used:")
        assert "is a required property" in follow_up

    async def test_an_invalid_result_twice_is_dropped(self, ground, scripted_model):
        invalid = result(seed_prompt=None)
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps(invalid, ensure_ascii=False)),
            model_reply(json.dumps(invalid, ensure_ascii=False)),
        )
        outcome = await ground()
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.invalid_output
        assert "seed_prompt" in (outcome.drop_detail or "")
        assert outcome.usage is not None
        assert outcome.usage.input_tokens == 30
        assert outcome.usage_complete

    async def test_the_drop_reports_the_follow_ups_problem(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps(result(seed_prompt=None), ensure_ascii=False)),
            model_reply(
                json.dumps(result(synthetic_user_info=None), ensure_ascii=False)
            ),
        )
        outcome = await ground()
        assert outcome.drop_reason == DropReason.invalid_output
        assert "synthetic_user_info" in (outcome.drop_detail or "")
        assert "seed_prompt" not in (outcome.drop_detail or "")

    async def test_args_that_are_not_an_object_are_retried(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps(result(args="[1, 2]"), ensure_ascii=False)),
            model_reply(json.dumps(result(), ensure_ascii=False)),
        )
        outcome = await ground()
        assert outcome.status == "grounded"
        assert "must be a JSON object" in sent_text(scripted_model.sent[2][-1])

    async def test_grounded_without_an_environment_is_dropped(
        self, ground, scripted_model
    ):
        scripted_model.script(model_reply(json.dumps(result(), ensure_ascii=False)))
        outcome = await ground()
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.invalid_output

    async def test_the_models_drop_is_kept(self, ground, scripted_model):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(
                json.dumps(
                    {
                        "status": "dropped",
                        "drop_reason": "unrepresentable",
                        "drop_detail": "The server doesn't enforce the rule.",
                        "seed_prompt": None,
                        "synthetic_user_info": None,
                        "reference": None,
                    },
                    ensure_ascii=False,
                )
            ),
        )
        outcome = await ground()
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.unrepresentable
        assert outcome.drop_detail == "The server doesn't enforce the rule."
        assert len(outcome.call_log) == 1


@pytest.mark.parametrize(
    "listed, expected",
    [
        (StructuredOutputMode.json_schema, StructuredOutputMode.json_schema),
        (
            StructuredOutputMode.json_instructions,
            StructuredOutputMode.json_instructions,
        ),
        (StructuredOutputMode.function_calling, StructuredOutputMode.json_schema),
        (StructuredOutputMode.function_calling_weak, StructuredOutputMode.json_schema),
        (StructuredOutputMode.default, StructuredOutputMode.json_schema),
    ],
)
def test_structured_output_mode_avoids_tool_calls(listed, expected):
    model, provider = next(
        (m, p)
        for m in built_in_models
        for p in m.providers
        if p.structured_output_mode == listed
    )
    assert structured_output_mode(model.name, provider.name) == expected


def test_structured_output_mode_for_an_unlisted_model():
    assert (
        structured_output_mode("not-a-model", ModelProviderName.openai)
        == StructuredOutputMode.json_schema
    )


class TestStops:
    async def test_calls_past_the_limit_end_the_run(
        self, ground, scripted_model, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start()),
            *(model_reply(None, READ_NOTES) for _ in range(10)),
        )
        outcome = await ground(
            limits=GroundingLimits(max_tool_calls=1, calls_after_limit=1)
        )
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.limit
        assert "1 tool calls" in (outcome.drop_detail or "")
        # Start, one call, one refused, the hard stop; at most one more model call
        # can start before the run is cancelled.
        assert 4 <= len(scripted_model.sent) <= 5
        assert outcome.usage is None
        assert not outcome.usage_complete
        await server_is_free()

    async def test_running_out_of_time_drops_the_case(
        self, ground, scripted_model, server_is_free
    ):
        async def stall():
            await asyncio.sleep(10)
            raise AssertionError("not reached")

        scripted_model.script(model_reply(None, start()), stall)
        outcome = await ground(time_limit_s=0.5)
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.limit
        assert "minute limit" in (outcome.drop_detail or "")
        assert not outcome.usage_complete
        assert [c.tool for c in outcome.call_log] == ["start_episode"]
        await server_is_free()

    async def test_an_environment_failure_is_raised(
        self, ground, scripted_model, session_manager, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(None, READ_NOTES),
            model_reply("never reached"),
        )
        with patch.object(
            session_manager,
            "call_tool",
            AsyncMock(side_effect=OpenEnvTransientError("connection dropped")),
        ):
            with pytest.raises(OpenEnvTransientError, match="connection dropped"):
                await ground()
        await server_is_free()

    async def test_a_model_failure_is_raised(
        self, ground, scripted_model, server_is_free
    ):
        async def fail():
            raise RuntimeError("provider down")

        scripted_model.script(model_reply(None, start()), fail)
        with pytest.raises(KilnRunError):
            await ground()
        await server_is_free()

    async def test_cancelling_releases_the_episode(
        self, ground, scripted_model, server_is_free
    ):
        started = asyncio.Event()

        async def stall():
            started.set()
            await asyncio.sleep(10)
            raise AssertionError("not reached")

        scripted_model.script(model_reply(None, start()), stall)
        task = asyncio.create_task(ground())
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await server_is_free()


MISBEHAVIOURS = {
    "empty reply": (DropReason.invalid_output, "empty reply", [model_reply(None)]),
    "answer and tools at once": (
        DropReason.invalid_output,
        "same turn",
        [model_reply(None, ("task_response", {}), READ_NOTES)],
    ),
    "endless tool rounds": (
        DropReason.limit,
        "rounds of tool calls",
        [model_reply(None, ("no_such_tool", {})) for _ in range(3)],
    ),
}
"""Model replies, after the case's first reset, that make the adapter end the run,
with the drop each one gives. The tool rounds need the `few_tool_rounds` fixture."""


@pytest.mark.parametrize("answer_style", ["structured_output", "submit_result"])
@pytest.mark.parametrize("misbehaviour", list(MISBEHAVIOURS))
async def test_a_misbehaving_model_drops_the_case(
    ground, scripted_model, server_is_free, few_tool_rounds, misbehaviour, answer_style
):
    reason, detail, replies = MISBEHAVIOURS[misbehaviour]
    scripted_model.script(model_reply(None, start()), *replies)
    outcome = await ground(answer_style=answer_style)
    assert outcome.status == "dropped"
    assert outcome.drop_reason == reason
    assert detail in (outcome.drop_detail or "")
    assert outcome.call_log[0].tool == "start_episode"
    assert not outcome.usage_complete
    await server_is_free()


class TestSubmitResult:
    async def test_an_empty_reply_after_the_submission_keeps_the_result(
        self, ground, scripted_model, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start("b")),
            model_reply(None, submit(**result(args={}))),
            model_reply(None),
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.status == "grounded"
        assert outcome.openenv_reset is not None
        assert outcome.openenv_reset.reset_kwargs == {"fixture_id": "b"}
        assert not outcome.usage_complete
        await server_is_free()

    async def test_a_provider_failure_after_the_submission_keeps_the_result(
        self, ground, scripted_model
    ):
        async def fail():
            raise litellm.AuthenticationError("bad key", "openai", "gpt-4")

        scripted_model.script(
            model_reply(None, start()),
            model_reply(None, submit(**result(args={}))),
            fail,
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.status == "grounded"
        assert not outcome.usage_complete

    async def test_an_accepted_result_grounds_the_case(
        self, ground, scripted_model, built_adapters, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start("b")),
            model_reply(None, submit(**result(args={"limit": 5}))),
            model_reply("done"),
        )
        outcome = await ground(answer_style="submit_result")

        assert outcome.status == "grounded"
        assert outcome.openenv_reset is not None
        assert outcome.openenv_reset.reset_kwargs == {"fixture_id": "b"}
        assert outcome.reference is not None
        assert outcome.reference.facts[0].evidence.args == {"limit": 5}
        assert "Recorded" in sent_text(scripted_model.sent[2][-1])
        [adapter] = built_adapters
        assert adapter.task.output_json_schema is None
        assert adapter.base_adapter_config.automatic_prompt_caching
        definitions = {
            d["function"]["name"]: d["function"]
            for d in await adapter.litellm_tools()  # type: ignore[attr-defined]
        }
        jsonschema.validate(
            result(args={"limit": 5}), definitions["submit_result"]["parameters"]
        )
        await server_is_free()

    async def test_an_invalid_result_gets_its_error_back(self, ground, scripted_model):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(None, submit(**result(args={}, seed_prompt=None))),
            model_reply(None, submit(**result(args={}))),
            model_reply("done"),
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.status == "grounded"
        error = sent_text(scripted_model.sent[2][-1])
        assert "can't be used" in error and "seed_prompt" in error

    async def test_two_invalid_results_drop_the_case(self, ground, scripted_model):
        invalid = submit(**result(args={}, seed_prompt=None))
        scripted_model.script(
            model_reply(None, start()),
            model_reply(None, invalid),
            model_reply(None, invalid),
            model_reply("done"),
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.invalid_output
        assert "seed_prompt" in (outcome.drop_detail or "")

    async def test_no_submission_gets_one_follow_up(self, ground, scripted_model):
        scripted_model.script(
            model_reply(None, start()),
            model_reply("All done."),
            model_reply("Still done."),
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.invalid_output
        assert NO_SUBMISSION_ERROR in (outcome.drop_detail or "")
        assert "Call submit_result" in scripted_model.sent[2][-1]["content"]

    async def test_a_submission_in_the_follow_up_grounds_the_case(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply("All done."),
            model_reply(None, submit(**result(args={}))),
            model_reply("done"),
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.status == "grounded"

    async def test_calls_after_the_submission_keep_the_result(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(None, submit(**result(args={}))),
            *(model_reply(None, start("b")) for _ in range(5)),
        )
        outcome = await ground(
            answer_style="submit_result", limits=GroundingLimits(calls_after_limit=1)
        )
        assert outcome.status == "grounded"
        assert outcome.openenv_reset is not None
        assert outcome.openenv_reset.reset_kwargs == {"fixture_id": "a"}

    async def test_a_second_submission_is_refused(self, ground, scripted_model):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(None, submit(**result(args={}))),
            model_reply(None, submit(**result(args={}, seed_prompt="changed"))),
            model_reply("done"),
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.seed_prompt == "Add the note 'hi' please."
        assert "already recorded" in sent_text(scripted_model.sent[3][-1])

    async def test_submissions_after_giving_up_are_refused(
        self, ground, scripted_model
    ):
        invalid = submit(**result(args={}, seed_prompt=None))
        scripted_model.script(
            model_reply(None, start()),
            model_reply(None, invalid),
            model_reply(None, invalid),
            model_reply(None, submit(**result(args={}))),
            model_reply("done"),
        )
        outcome = await ground(answer_style="submit_result")
        assert outcome.drop_reason == DropReason.invalid_output
        assert "could not be used" in sent_text(scripted_model.sent[4][-1])


async def test_a_follow_up_that_keeps_calling_tools_is_a_limit_drop(
    ground, scripted_model
):
    scripted_model.script(
        model_reply(None, start()),
        model_reply("not json"),
        *(model_reply(None, READ_NOTES) for _ in range(5)),
    )
    outcome = await ground(limits=GroundingLimits(calls_after_limit=1))
    assert outcome.drop_reason == DropReason.limit
    assert "asked only for its result" in (outcome.drop_detail or "")


SINGLE_TURN_CASE = GroundingCase(scenario="A clerk asks to add a note.")

SINGLE_TURN_CONTEXT = EvalContext(
    specification="The agent adds notes when asked.",
    target_task_prompt="Help clerks keep notes.",
    mode="single_turn",
    input_schema=json.dumps(
        {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        }
    ),
)


def single_turn_result(
    *, input: str, args: Any = '{"limit": 5}', **overrides: Any
) -> dict[str, Any]:
    """A grounded single-turn result as the model returns it: an input, no user."""
    fields = result(args=args, **overrides)
    del fields["seed_prompt"], fields["synthetic_user_info"]
    return {**fields, "input": input}


class TestSingleTurn:
    async def test_the_agent_writes_the_input(
        self, ground, scripted_model, built_adapters
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(
                json.dumps(
                    single_turn_result(input='{"note": "hi"}'), ensure_ascii=False
                )
            ),
        )
        outcome = await ground(SINGLE_TURN_CASE, eval_context=SINGLE_TURN_CONTEXT)

        assert outcome.status == "grounded"
        assert outcome.input == '{"note": "hi"}'
        assert outcome.seed_prompt is None and outcome.synthetic_user_info is None
        [adapter] = built_adapters
        schema = json.loads(adapter.task.output_json_schema or "{}")
        assert "input" in schema["properties"]
        assert "seed_prompt" not in schema["properties"]
        system, user = scripted_model.sent[0][:2]
        assert "5. Write the input:" in system["content"]
        assert "<input_schema>" in user["content"]
        assert "<simulated_user>" not in user["content"]

    async def test_an_input_off_the_task_schema_is_retried(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(
                json.dumps(
                    single_turn_result(input='{"text": "hi"}'), ensure_ascii=False
                )
            ),
            model_reply(
                json.dumps(
                    single_turn_result(input='{"note": "hi"}'), ensure_ascii=False
                )
            ),
        )
        outcome = await ground(SINGLE_TURN_CASE, eval_context=SINGLE_TURN_CONTEXT)
        assert outcome.status == "grounded"
        follow_up = scripted_model.sent[2][-1]["content"]
        assert INPUT_SCHEMA_MISMATCH in follow_up

    async def test_an_input_off_the_task_schema_twice_is_dropped(
        self, ground, scripted_model
    ):
        off_schema = json.dumps(
            single_turn_result(input="not json"), ensure_ascii=False
        )
        scripted_model.script(
            model_reply(None, start()),
            model_reply(off_schema),
            model_reply(off_schema),
        )
        outcome = await ground(SINGLE_TURN_CASE, eval_context=SINGLE_TURN_CONTEXT)
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.invalid_output
        assert INPUT_SCHEMA_MISMATCH in (outcome.drop_detail or "")

    async def test_submit_result_reports_an_input_off_the_task_schema(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(
                None, submit(**single_turn_result(input='{"text": "hi"}', args={}))
            ),
            model_reply(
                None, submit(**single_turn_result(input='{"note": "hi"}', args={}))
            ),
            model_reply("done"),
        )
        outcome = await ground(
            SINGLE_TURN_CASE,
            eval_context=SINGLE_TURN_CONTEXT,
            answer_style="submit_result",
        )
        assert outcome.status == "grounded"
        assert outcome.input == '{"note": "hi"}'
        error = sent_text(scripted_model.sent[2][-1])
        assert "can't be used" in error and "input schema" in error

    async def test_a_multi_turn_result_twice_in_single_turn_mode_is_dropped(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps(result(), ensure_ascii=False)),
            model_reply(json.dumps(result(), ensure_ascii=False)),
        )
        outcome = await ground(
            SINGLE_TURN_CASE,
            eval_context=SINGLE_TURN_CONTEXT.model_copy(update={"input_schema": None}),
            answer_style="submit_result",
        )
        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.invalid_output


REPLY = "I added the note 'hi'."

REHEARSING = EVAL_CONTEXT.model_copy(update={"rehearse": True})


def rehearsed(**overrides: Any) -> dict[str, Any]:
    """A grounded result with the rehearsal reply a rehearsing prompt asks for."""
    return result(rehearsal_reply=REPLY, **overrides)


class TestRehearsal:
    async def test_a_grounded_case_keeps_its_last_episode_as_a_trace(
        self, ground, scripted_model, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start("a")),
            model_reply(None, ("append_note", {"note": "exploring"})),
            model_reply(None, start("a")),
            model_reply(None, READ_NOTES),
            model_reply(None, ("append_note", {"note": "hi"})),
            model_reply(None, ("read_state", {})),
            model_reply(json.dumps(rehearsed(), ensure_ascii=False)),
        )
        outcome = await ground(eval_context=REHEARSING)

        assert outcome.status == "grounded"
        episode = outcome.rehearsal_episode
        assert episode is not None and episode.final_state is not None
        assert episode.final_state["notes"] == ["hi"]
        assert episode.reset == outcome.openenv_reset
        read_notes, append_note = outcome.call_log[3], outcome.call_log[4]
        assert outcome.rehearsal_trace == [
            {"role": "system", "content": "Help clerks keep notes."},
            {"role": "user", "content": "Add the note 'hi' please."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "rehearsal_call_0",
                        "type": "function",
                        "function": {"name": "read_notes", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "rehearsal_call_0",
                "content": read_notes.output,
                "is_error": None,
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "rehearsal_call_1",
                        "type": "function",
                        "function": {
                            "name": "append_note",
                            "arguments": '{"note": "hi"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "rehearsal_call_1",
                "content": append_note.output,
                "is_error": None,
            },
            {"role": "assistant", "content": "I added the note 'hi'."},
        ]
        await server_is_free()

    async def test_a_submitted_result_keeps_the_final_state(
        self, ground, scripted_model, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start("b")),
            model_reply(None, ("append_note", {"note": "hi"})),
            model_reply(None, submit(**rehearsed(args={"limit": 5}))),
            model_reply("done"),
        )
        outcome = await ground(answer_style="submit_result", eval_context=REHEARSING)

        assert outcome.rehearsal_episode is not None
        assert outcome.rehearsal_episode.final_state is not None
        assert outcome.rehearsal_episode.final_state["notes"] == ["hi"]
        assert outcome.rehearsal_trace is not None
        assert outcome.rehearsal_trace[-1]["content"] == "I added the note 'hi'."
        await server_is_free()

    async def test_a_single_turn_rehearsal_opens_with_the_input(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(
                json.dumps(
                    single_turn_result(input='{"note": "hi"}', rehearsal_reply=REPLY),
                    ensure_ascii=False,
                )
            ),
        )
        outcome = await ground(
            SINGLE_TURN_CASE,
            eval_context=SINGLE_TURN_CONTEXT.model_copy(update={"rehearse": True}),
        )

        assert outcome.rehearsal_trace is not None
        assert outcome.rehearsal_trace[1] == {
            "role": "user",
            "content": '{"note": "hi"}',
        }

    async def test_without_a_reply_there_is_no_rehearsal(self, ground, scripted_model):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps(result(rehearsal_reply=" "), ensure_ascii=False)),
        )
        outcome = await ground(eval_context=REHEARSING)

        assert outcome.status == "grounded"
        assert outcome.rehearsal_trace is None
        assert outcome.rehearsal_episode is None

    async def test_a_dropped_case_releases_its_episode_unread(
        self, ground, scripted_model, session_manager, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(
                json.dumps(
                    result(
                        status="dropped",
                        drop_reason="no_fit",
                        drop_detail="Nothing fits.",
                        seed_prompt=None,
                        synthetic_user_info=None,
                        rehearsal_reply=None,
                        reference=None,
                    ),
                    ensure_ascii=False,
                )
            ),
        )
        with patch.object(
            session_manager, "end_episode", wraps=session_manager.end_episode
        ) as end_episode:
            outcome = await ground(eval_context=REHEARSING)

        assert outcome.status == "dropped"
        assert outcome.rehearsal_trace is None
        end_episode.assert_not_called()
        await server_is_free()

    async def test_a_result_only_on_the_follow_up_has_no_rehearsal(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start("a")),
            model_reply("not json at all"),
            model_reply(json.dumps(rehearsed(), ensure_ascii=False)),
        )
        outcome = await ground(eval_context=REHEARSING)

        assert outcome.status == "grounded"
        assert outcome.rehearsal_trace is None
        assert outcome.rehearsal_episode is None

    async def test_a_result_only_on_the_follow_up_says_why_it_has_none(
        self, ground, scripted_model
    ):
        scripted_model.script(
            model_reply(None, start("a")),
            model_reply("not json at all"),
            model_reply(json.dumps(rehearsed(), ensure_ascii=False)),
        )
        outcome = await ground(eval_context=REHEARSING)

        assert outcome.rehearsal_skipped is not None
        assert "final state" in outcome.rehearsal_skipped

    async def test_facts_read_under_other_reset_arguments_keep_no_rehearsal(
        self, ground, scripted_model, server_is_free
    ):
        scripted_model.script(
            model_reply(None, start("b")),
            model_reply(None, READ_NOTES),
            model_reply(None, start("a")),
            model_reply(None, ("append_note", {"note": "hi"})),
            model_reply(json.dumps(rehearsed(args="{}"), ensure_ascii=False)),
        )
        outcome = await ground(eval_context=REHEARSING)

        assert outcome.status == "grounded"
        assert outcome.openenv_reset is not None
        assert outcome.openenv_reset.reset_kwargs == {"fixture_id": "a"}
        assert outcome.rehearsal_trace is None
        assert outcome.rehearsal_episode is None
        assert outcome.rehearsal_skipped is not None
        assert "other reset arguments" in outcome.rehearsal_skipped
        await server_is_free()

    async def test_facts_read_under_the_saved_reset_keep_the_rehearsal(
        self, ground, scripted_model
    ):
        # An earlier episode on other reset arguments doesn't matter when the
        # evidence was read under the reset the case is saved with.
        scripted_model.script(
            model_reply(None, start("b")),
            model_reply(None, ("append_note", {"note": "exploring"})),
            model_reply(None, start("a")),
            model_reply(None, READ_NOTES),
            model_reply(None, start("a")),
            model_reply(None, ("append_note", {"note": "hi"})),
            model_reply(json.dumps(rehearsed(args="{}"), ensure_ascii=False)),
        )
        outcome = await ground(eval_context=REHEARSING)

        assert outcome.rehearsal_trace is not None
        assert outcome.rehearsal_skipped is None

    async def test_a_slow_final_state_read_keeps_the_case_without_a_rehearsal(
        self, ground, scripted_model, session_manager, server_is_free
    ):
        release = session_manager.release

        async def slow_end_episode(episode):
            try:
                await asyncio.sleep(30)
            finally:
                await release(episode)

        scripted_model.script(
            model_reply(None, start("a")),
            model_reply(None, ("append_note", {"note": "hi"})),
            model_reply(json.dumps(rehearsed(), ensure_ascii=False)),
        )
        with (
            patch("kiln_ai.eval_grounding.session.FINAL_STATE_TIMEOUT_S", 0.05),
            patch.object(session_manager, "end_episode", side_effect=slow_end_episode),
        ):
            outcome = await ground(eval_context=REHEARSING)

        assert outcome.status == "grounded"
        assert outcome.rehearsal_trace is None
        assert outcome.rehearsal_skipped is not None
        await server_is_free()


class TestWithoutARehearsalJudge:
    """With `rehearse` off, grounding behaves as it did before rehearsals existed."""

    @pytest.mark.parametrize("answer_style", ["structured_output", "submit_result"])
    async def test_the_episode_is_released_unread(
        self, ground, scripted_model, session_manager, server_is_free, answer_style
    ):
        final = (
            [
                model_reply(None, submit(**result(args={"limit": 5}))),
                model_reply("done"),
            ]
            if answer_style == "submit_result"
            else [model_reply(json.dumps(result(), ensure_ascii=False))]
        )
        scripted_model.script(
            model_reply(None, start("a")),
            model_reply(None, ("append_note", {"note": "hi"})),
            *final,
        )
        with (
            patch.object(
                session_manager, "end_episode", wraps=session_manager.end_episode
            ) as end_episode,
            patch.object(
                session_manager, "release", wraps=session_manager.release
            ) as release,
        ):
            outcome = await ground(answer_style=answer_style)

        assert outcome.status == "grounded"
        assert outcome.rehearsal_trace is None
        assert outcome.rehearsal_episode is None
        assert outcome.rehearsal_skipped is None
        end_episode.assert_not_called()
        release.assert_called_once()
        await server_is_free()

    async def test_the_model_gets_the_prompt_and_schema_without_a_rehearsal(
        self, ground, scripted_model, built_adapters
    ):
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps(result(), ensure_ascii=False)),
        )
        await ground()

        task = built_adapters[0].task
        assert task.instruction == system_prompt(
            GroundingLimits(), 30, "structured_output", "multi_turn"
        )
        assert "rehearsal_reply" not in (task.output_json_schema or "")
        assert "rehearsal_reply" not in task.instruction

    async def test_a_rehearsal_reply_is_refused_by_the_schema(
        self, ground, scripted_model
    ):
        # The strict schema is the same as before rehearsals existed, so a reply
        # with the extra field is off it.
        scripted_model.script(
            model_reply(None, start()),
            model_reply(json.dumps(rehearsed(), ensure_ascii=False)),
            model_reply(json.dumps(rehearsed(), ensure_ascii=False)),
        )
        outcome = await ground()

        assert outcome.status == "dropped"
        assert outcome.drop_reason == DropReason.invalid_output
