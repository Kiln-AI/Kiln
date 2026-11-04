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
from kiln_ai.adapters.ml_model_list import ModelName, ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel import Project, Task, TaskRun
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import AddTool
from kiln_ai.utils.config import Config

RESPONSES_URL = "https://api.openai.com/v1/responses"
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
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=ModelName.gpt_5_4_pro,
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            thinking_level="medium",
        ),
        base_adapter_config=AdapterConfig(allow_saving=False),
    )
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
