"""Offline wire tests for OpenAI models that LiteLLM routes to /v1/responses.

These run real LiteLLM through LiteLlmAdapter, with respx standing in for OpenAI,
so they catch LiteLLM upgrades that change what reaches the wire.
"""

import json
from typing import Any
from unittest.mock import Mock, patch

import httpx
import litellm
import pytest
import respx

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.errors import (
    REASONING_SUMMARY_VERIFICATION_ERROR_MESSAGE,
    KilnRunError,
)
from kiln_ai.adapters.ml_model_list import (
    ModelName,
    ModelProviderName,
    built_in_models,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.datamodel import Project, Task, TaskRun
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import AddTool
from kiln_ai.utils.config import Config

RESPONSES_URL = "https://api.openai.com/v1/responses"
CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
API_KEY = "sk-test-openai-key"

REASONING_ITEM = {
    "type": "reasoning",
    "id": "rs_1",
    "summary": [{"type": "summary_text", "text": "Need to add."}],
    "encrypted_content": "ENC_RS_1",
}
NARRATION_MESSAGE = {
    "type": "message",
    "id": "msg_0",
    "status": "completed",
    "role": "assistant",
    "content": [
        {"type": "output_text", "text": "Let me add those.", "annotations": []}
    ],
}
ADD_CALL = {
    "type": "function_call",
    "id": "fc_1",
    "call_id": "call_add",
    "name": "add",
    "arguments": '{"a": 2, "b": 2}',
    "status": "completed",
}
FINAL_MESSAGE = {
    "type": "message",
    "id": "msg_1",
    "status": "completed",
    "role": "assistant",
    "content": [
        {"type": "output_text", "text": "The answer is [4]", "annotations": []}
    ],
}


# GPT-5.6+ often split reasoning into several items, each with several summary parts.
TWO_PART_ITEM = {
    "type": "reasoning",
    "id": "rs_two_parts",
    "summary": [
        {"type": "summary_text", "text": "**Plan**\n\nFirst part."},
        {"type": "summary_text", "text": "**Check**\n\nSecond part."},
    ],
    "encrypted_content": "ENC_TWO_PARTS",
}
ONE_PART_ITEM = {
    "type": "reasoning",
    "id": "rs_one_part",
    "summary": [{"type": "summary_text", "text": "One more thought."}],
    "encrypted_content": "ENC_ONE_PART",
}

SUMMARY_PROVIDER_MODELS = [
    model.name
    for model in built_in_models
    for provider in model.providers
    if provider.name == ModelProviderName.openai
    and provider.openai_reasoning_summary is not None
]

SUMMARY_PROVIDER_LEVELS = [
    pytest.param(model.name, level, id=f"{model.name}-{level}")
    for model in built_in_models
    for provider in model.providers
    if provider.name == ModelProviderName.openai
    and provider.openai_reasoning_summary is not None
    for level in (provider.available_thinking_levels or {}).values()
]

UNVERIFIED_ORG_ERROR = {
    "error": {
        "message": (
            "Your organization must be verified to generate reasoning summaries. "
            "Please go to: https://platform.openai.com/settings/organization/general "
            "and click on Verify Organization. If you just verified, it can take up "
            "to 15 minutes for access to propagate."
        ),
        "type": "invalid_request_error",
        "param": "reasoning.summary",
        "code": "unsupported_value",
    }
}


def responses_body(output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1759000000,
        "status": "completed",
        "model": "gpt-5.4-pro",
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "output": output,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 3},
        },
    }


def responses_stream_events(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Responses SSE events OpenAI sends for `output`, each text split in two deltas."""
    events: list[dict[str, Any]] = [
        {
            "type": "response.created",
            "response": {**responses_body([]), "status": "in_progress"},
        }
    ]
    for output_index, item in enumerate(output):
        at = {"output_index": output_index}
        if item["type"] == "reasoning":
            events.append(
                {
                    "type": "response.output_item.added",
                    **at,
                    "item": {**item, "summary": [], "encrypted_content": None},
                }
            )
            for summary_index, part in enumerate(item["summary"]):
                part_at = {**at, "item_id": item["id"], "summary_index": summary_index}
                text = part["text"]
                events.append(
                    {
                        "type": "response.reasoning_summary_part.added",
                        **part_at,
                        "part": {"type": "summary_text", "text": ""},
                    }
                )
                for delta in (text[:6], text[6:]):
                    events.append(
                        {
                            "type": "response.reasoning_summary_text.delta",
                            **part_at,
                            "delta": delta,
                        }
                    )
                events.append(
                    {
                        "type": "response.reasoning_summary_text.done",
                        **part_at,
                        "text": text,
                    }
                )
        elif item["type"] == "message":
            events.append(
                {
                    "type": "response.output_item.added",
                    **at,
                    "item": {**item, "status": "in_progress", "content": []},
                }
            )
            events.append(
                {
                    "type": "response.output_text.delta",
                    **at,
                    "item_id": item["id"],
                    "content_index": 0,
                    "delta": item["content"][0]["text"],
                }
            )
        else:
            events.append(
                {
                    "type": "response.output_item.added",
                    **at,
                    "item": {**item, "arguments": "", "status": "in_progress"},
                }
            )
            events.append(
                {
                    "type": "response.function_call_arguments.delta",
                    **at,
                    "item_id": item["id"],
                    "delta": item["arguments"],
                }
            )
        events.append({"type": "response.output_item.done", **at, "item": item})
    events.append({"type": "response.completed", "response": responses_body(output)})
    return [{**event, "sequence_number": number} for number, event in enumerate(events)]


def streamed_responses_reply(output: list[dict[str, Any]]) -> httpx.Response:
    sse = "".join(
        f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        for event in responses_stream_events(output)
    )
    return httpx.Response(
        200, content=sse.encode(), headers={"content-type": "text/event-stream"}
    )


def chat_completion_reply(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1759000000,
            "model": "gpt-6.1-sol",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def openai_adapter(task: Task, model_name: str, **run_config: Any) -> BaseAdapter:
    return adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            **run_config,
        ),
        base_adapter_config=AdapterConfig(allow_saving=False),
    )


async def run_streamed(adapter: BaseAdapter, input: str) -> tuple[TaskRun, list[Any]]:
    stream = adapter.invoke_openai_stream(input)
    chunks = [chunk async for chunk in stream]
    return stream.task_run, chunks


async def run_with(invocation: str, adapter: BaseAdapter, input: str) -> TaskRun:
    if invocation == "invoke":
        return await adapter.invoke(input)
    run, _ = await run_streamed(adapter, input)
    return run


@pytest.fixture
def summaries_on():
    Config.shared().open_ai_reasoning_summaries = True


@pytest.fixture(autouse=True)
def use_httpx_transport(monkeypatch):
    # LiteLLM sends through aiohttp by default, which respx can't intercept.
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)


@pytest.fixture(autouse=True)
def openai_key():
    Config.shared().open_ai_api_key = API_KEY


@pytest.fixture
def plain_task(tmp_path):
    project = Project(name="Test Project", path=str(tmp_path / "project.kiln"))
    project.save_to_file()
    task = Task(name="Test Task", instruction="Use tools for math", parent=project)
    task.save_to_file()
    return task


async def run_add_tool_loop(
    task: Task, first_output: list[dict[str, Any]]
) -> tuple[TaskRun, respx.Route, Mock]:
    """Runs gpt-5.4-pro with an add tool: the first reply is `first_output`, the second is FINAL_MESSAGE."""
    route = respx.post(RESPONSES_URL).mock(
        side_effect=[
            httpx.Response(200, json=responses_body(first_output)),
            httpx.Response(200, json=responses_body([FINAL_MESSAGE])),
        ]
    )
    adapter = openai_adapter(task, ModelName.gpt_5_4_pro, thinking_level="medium")
    add_spy = Mock(wraps=AddTool())
    with patch.object(adapter, "available_tools", return_value=[add_spy]):
        run = await adapter.invoke("what is 2+2")
    return run, route, add_spy


def request_body(route: respx.Route, call_index: int) -> dict[str, Any]:
    return json.loads(route.calls[call_index].request.content)


@respx.mock
async def test_tool_call_on_bridged_model_completes(plain_task):
    run, route, add_spy = await run_add_tool_loop(
        plain_task, [REASONING_ITEM, ADD_CALL]
    )

    assert run.output.output == "The answer is [4]"
    add_spy.run.assert_called_once()
    assert add_spy.run.call_args.kwargs == {"a": 2, "b": 2}
    [tool_output] = [
        item
        for item in request_body(route, 1)["input"]
        if item.get("type") == "function_call_output"
    ]
    assert tool_output["call_id"] == "call_add"
    # Responses accepts the output as a string or as a list of input_text parts.
    assert tool_output["output"] in ("4", [{"type": "input_text", "text": "4"}])


@respx.mock
async def test_bridged_requests_go_to_responses_with_store_false(plain_task):
    _, route, _ = await run_add_tool_loop(plain_task, [REASONING_ITEM, ADD_CALL])

    assert route.call_count == 2
    for call_index in range(2):
        assert request_body(route, call_index)["store"] is False


@respx.mock
async def test_reply_with_text_and_tool_call_runs_tool(plain_task):
    run, _, add_spy = await run_add_tool_loop(
        plain_task, [REASONING_ITEM, NARRATION_MESSAGE, ADD_CALL]
    )

    add_spy.run.assert_called_once()
    assert run.output.output == "The answer is [4]"
    assert run.trace is not None
    narration_turn = run.trace[2]
    assert narration_turn["role"] == "assistant"
    assert narration_turn.get("content") == "Let me add those."
    tool_calls = narration_turn.get("tool_calls")
    assert tool_calls is not None
    assert [call["function"]["name"] for call in tool_calls] == ["add"]


# Chat Completions rejects function tools with reasoning on for these models, so every
# tool run above `none` must reach Responses. At `none` it stays on Chat Completions.
@respx.mock
@pytest.mark.parametrize(("model_name", "thinking_level"), SUMMARY_PROVIDER_LEVELS)
async def test_tool_runs_use_responses_unless_thinking_is_off(
    plain_task, model_name, thinking_level
):
    responses_route = respx.post(RESPONSES_URL).mock(
        return_value=httpx.Response(200, json=responses_body([FINAL_MESSAGE]))
    )
    chat_route = respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=chat_completion_reply("The answer is [4]")
    )
    adapter = openai_adapter(plain_task, model_name, thinking_level=thinking_level)

    with patch.object(adapter, "available_tools", return_value=[AddTool()]):
        run = await adapter.invoke("what is 2+2")

    assert run.output.output == "The answer is [4]"
    expected_route, unused_route = (
        (chat_route, responses_route)
        if thinking_level == "none"
        else (responses_route, chat_route)
    )
    assert expected_route.call_count == 1
    assert not unused_route.called


@respx.mock
@pytest.mark.parametrize("model_name", SUMMARY_PROVIDER_MODELS)
async def test_summaries_on_streams_to_responses_with_summary(
    plain_task, summaries_on, model_name
):
    route = respx.post(RESPONSES_URL).mock(
        return_value=streamed_responses_reply([REASONING_ITEM, FINAL_MESSAGE])
    )

    run = await openai_adapter(plain_task, model_name).invoke("what is 2+2")

    assert run.output.output == "The answer is [4]"
    assert route.call_count == 1
    body = request_body(route, 0)
    assert body["reasoning"]["summary"] == "auto"
    assert body["stream"] is True
    assert body["store"] is False


@respx.mock
async def test_summaries_on_reports_same_usage_and_cost_as_non_streamed(plain_task):
    output = [REASONING_ITEM, FINAL_MESSAGE]
    respx.post(RESPONSES_URL).mock(
        side_effect=[
            httpx.Response(200, json=responses_body(output)),
            streamed_responses_reply(output),
        ]
    )
    adapter = openai_adapter(plain_task, ModelName.gpt_5_4_pro, thinking_level="medium")
    non_streamed = await adapter.invoke("what is 2+2")

    Config.shared().open_ai_reasoning_summaries = True
    adapter = openai_adapter(plain_task, ModelName.gpt_5_4_pro, thinking_level="medium")
    streamed = await adapter.invoke("what is 2+2")

    assert non_streamed.usage is not None and streamed.usage is not None
    assert streamed.usage.cost is not None
    for field in ("input_tokens", "output_tokens", "total_tokens", "cost"):
        assert getattr(streamed.usage, field) == getattr(non_streamed.usage, field)


@respx.mock
async def test_summaries_off_sends_no_summary(plain_task):
    route = respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=chat_completion_reply("The answer is [4]")
    )

    run = await openai_adapter(
        plain_task, ModelName.gpt_6_1_sol, thinking_level="medium"
    ).invoke("what is 2+2")

    assert run.output.output == "The answer is [4]"
    body = request_body(route, 0)
    assert body["reasoning_effort"] == "medium"
    for key in ("reasoning_summary", "reasoning", "stream"):
        assert key not in body


@respx.mock
@pytest.mark.parametrize("invocation", ["invoke", "invoke_openai_stream"])
async def test_multi_part_summary_saved_in_full(plain_task, summaries_on, invocation):
    # The one-part item comes first: the next item restarts at summary part 0, so the
    # break between them is only visible in the reasoning items, not in the deltas.
    respx.post(RESPONSES_URL).mock(
        return_value=streamed_responses_reply(
            [ONE_PART_ITEM, TWO_PART_ITEM, FINAL_MESSAGE]
        )
    )
    adapter = openai_adapter(plain_task, ModelName.gpt_6_1_sol, thinking_level="medium")

    run = await run_with(invocation, adapter, "what is 2+2")

    full_summary = (
        "One more thought.\n\n**Plan**\n\nFirst part.\n\n**Check**\n\nSecond part."
    )
    assert run.intermediate_outputs == {"reasoning": full_summary}
    assert run.trace is not None
    assert run.trace[-1].get("reasoning_content") == full_summary


@respx.mock
async def test_streamed_reasoning_deltas_on_one_choice_with_part_breaks(
    plain_task, summaries_on
):
    respx.post(RESPONSES_URL).mock(
        return_value=streamed_responses_reply(
            [TWO_PART_ITEM, ONE_PART_ITEM, FINAL_MESSAGE]
        )
    )
    adapter = openai_adapter(plain_task, ModelName.gpt_6_1_sol, thinking_level="medium")

    run, chunks = await run_streamed(adapter, "what is 2+2")

    reasoning_choices = [
        choice
        for chunk in chunks
        for choice in chunk.choices
        if getattr(choice.delta, "reasoning_content", None)
    ]
    assert {choice.index for choice in reasoning_choices} == {0}
    streamed_text = "".join(
        choice.delta.reasoning_content for choice in reasoning_choices
    )
    assert streamed_text == (
        "**Plan**\n\nFirst part.\n\n**Check**\n\nSecond part.\n\nOne more thought."
    )
    assert run.intermediate_outputs == {"reasoning": streamed_text}


@respx.mock
@pytest.mark.parametrize(
    "invocation,summaries",
    [("invoke", True), ("invoke_openai_stream", False)],
)
async def test_streamed_tool_loop_replays_reasoning_items(
    plain_task, invocation, summaries
):
    Config.shared().open_ai_reasoning_summaries = summaries
    route = respx.post(RESPONSES_URL).mock(
        side_effect=[
            streamed_responses_reply([TWO_PART_ITEM, ONE_PART_ITEM, ADD_CALL]),
            streamed_responses_reply([FINAL_MESSAGE]),
        ]
    )
    adapter = openai_adapter(plain_task, ModelName.gpt_5_4_pro, thinking_level="medium")

    with patch.object(adapter, "available_tools", return_value=[AddTool()]):
        run = await run_with(invocation, adapter, "what is 2+2")

    assert run.output.output == "The answer is [4]"
    round_two_input = request_body(route, 1)["input"]
    replayed = [
        (item["id"], item["encrypted_content"])
        for item in round_two_input
        if item.get("type") == "reasoning"
    ]
    assert replayed == [
        ("rs_two_parts", "ENC_TWO_PARTS"),
        ("rs_one_part", "ENC_ONE_PART"),
    ]
    input_types = [item.get("type") for item in round_two_input]
    assert input_types.index("reasoning") < input_types.index("function_call")


@respx.mock
async def test_unverified_org_error_message(plain_task, summaries_on):
    respx.post(RESPONSES_URL).mock(
        return_value=httpx.Response(400, json=UNVERIFIED_ORG_ERROR)
    )
    adapter = openai_adapter(plain_task, ModelName.gpt_6_1_sol, thinking_level="medium")

    with pytest.raises(KilnRunError) as exc_info:
        await adapter.invoke("what is 2+2")

    assert str(exc_info.value) == REASONING_SUMMARY_VERIFICATION_ERROR_MESSAGE
    assert isinstance(exc_info.value.original, litellm.BadRequestError)
