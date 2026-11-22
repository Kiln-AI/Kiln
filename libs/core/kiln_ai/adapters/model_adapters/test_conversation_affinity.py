"""Tests for conversation and prompt affinity keys, including offline wire tests that run real
LiteLLM with respx standing in for each provider, so a LiteLLM upgrade that changes
where the key lands (body param, header, or dropped) fails here."""

import json
from typing import Any
from unittest.mock import patch

import httpx
import litellm
import pytest
import respx
from litellm.types.utils import Message as LiteLLMMessage

from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.conversation_affinity import (
    affinity_completion_kwargs,
    conversation_affinity_key,
    prompt_affinity_key,
)
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

SYSTEM = {"role": "system", "content": "You are helpful."}
FIRST_USER = {"role": "user", "content": "What is 2+2?"}
TURN_ONE = [SYSTEM, FIRST_USER]
TURN_TWO = [
    SYSTEM,
    FIRST_USER,
    {"role": "assistant", "content": "4"},
    {"role": "user", "content": "And 3+3?"},
]
TOOL_ROUND = [
    SYSTEM,
    FIRST_USER,
    LiteLLMMessage(role="assistant", content=None),
    {"role": "tool", "tool_call_id": "call_1", "content": "4"},
]
OTHER_CONVERSATION_SAME_PROMPT = [SYSTEM, {"role": "user", "content": "What is 5+5?"}]
OTHER_PROMPT = [{"role": "system", "content": "Be terse."}, FIRST_USER]


@pytest.mark.parametrize("key_fn", [conversation_affinity_key, prompt_affinity_key])
@pytest.mark.parametrize("messages", [TURN_TWO, TOOL_ROUND])
def test_keys_are_stable_across_turns_and_tool_rounds(key_fn, messages):
    assert key_fn(messages) == key_fn(TURN_ONE)


@pytest.mark.parametrize(
    "other_opening", [OTHER_CONVERSATION_SAME_PROMPT, OTHER_PROMPT, [FIRST_USER]]
)
def test_conversation_key_differs_between_conversations(other_opening):
    assert conversation_affinity_key(other_opening) != conversation_affinity_key(
        TURN_ONE
    )


def test_prompt_key_is_shared_by_conversations_with_the_same_system_prompt():
    assert prompt_affinity_key(OTHER_CONVERSATION_SAME_PROMPT) == prompt_affinity_key(
        TURN_ONE
    )


@pytest.mark.parametrize(
    "other_prompt",
    [
        OTHER_PROMPT,
        [{"role": "developer", "content": "You are helpful."}, FIRST_USER],
        [SYSTEM, {"role": "system", "content": "Use tools."}, FIRST_USER],
    ],
)
def test_prompt_key_differs_between_system_prompts(other_prompt):
    assert prompt_affinity_key(other_prompt) != prompt_affinity_key(TURN_ONE)


def test_prompt_key_without_system_prompt_is_the_conversation_key():
    messages = [FIRST_USER, {"role": "assistant", "content": "4"}]

    assert prompt_affinity_key(messages) == conversation_affinity_key(messages)
    assert prompt_affinity_key(messages) is not None


@pytest.mark.parametrize("key_fn", [conversation_affinity_key, prompt_affinity_key])
def test_keys_fit_provider_length_limits(key_fn):
    key = key_fn(TURN_ONE)

    assert key is not None
    # OpenAI caps prompt_cache_key at 64 characters, OpenRouter session_id at 256.
    assert len(key) <= 64
    assert key.isalnum()


def test_key_ignores_dict_key_order_in_content_parts():
    parts = [{"type": "text", "text": "Describe this"}, {"type": "image_url"}]
    reordered = [{"text": "Describe this", "type": "text"}, {"type": "image_url"}]

    assert conversation_affinity_key(
        [{"role": "user", "content": parts}]
    ) == conversation_affinity_key([{"role": "user", "content": reordered}])


@pytest.mark.parametrize("messages", [[], [SYSTEM]])
def test_no_affinity_without_user_message(messages):
    assert conversation_affinity_key(messages) is None
    assert affinity_completion_kwargs(ModelProviderName.openai, messages) == {}


PROMPT_KEYED_PARAM: dict[ModelProviderName, str] = {
    ModelProviderName.openai: "prompt_cache_key",
    ModelProviderName.together_ai: "prompt_cache_key",
}
CONVERSATION_KEYED_PARAM: dict[ModelProviderName, str] = {
    ModelProviderName.openrouter: "session_id",
}


@pytest.mark.parametrize("provider_name", list(ModelProviderName))
def test_kwargs_send_keys_only_in_params_the_provider_reads(provider_name):
    conversation_key = conversation_affinity_key(TURN_ONE)
    expected = {"litellm_session_id": conversation_key}
    if provider_name in CONVERSATION_KEYED_PARAM:
        expected[CONVERSATION_KEYED_PARAM[provider_name]] = conversation_key
    if provider_name in PROMPT_KEYED_PARAM:
        expected[PROMPT_KEYED_PARAM[provider_name]] = prompt_affinity_key(TURN_ONE)

    assert affinity_completion_kwargs(provider_name, TURN_ONE) == expected


@pytest.fixture
def plain_task(tmp_path):
    project = Project(name="Test Project", path=str(tmp_path / "project.kiln"))
    project.save_to_file()
    task = Task(name="Test Task", instruction="Answer briefly", parent=project)
    task.save_to_file()
    return task


def make_adapter(
    task: Task,
    provider_name: ModelProviderName,
    additional_body_options: dict[str, Any] | None = None,
) -> LiteLlmAdapter:
    adapter = LiteLlmAdapter(
        config=LiteLlmConfig(
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="test-model",
                model_provider_name=provider_name,
                prompt_id="simple_prompt_builder",
                structured_output_mode="default",
            ),
            additional_body_options={"api_key": "test-key"}
            | (additional_body_options or {}),
        ),
        kiln_task=task,
        base_adapter_config=AdapterConfig(allow_saving=False),
    )
    adapter._model_provider = KilnModelProvider(name=provider_name, model_id="m")
    return adapter


async def test_explicit_body_option_overrides_affinity_key(plain_task):
    adapter = make_adapter(
        plain_task,
        ModelProviderName.openai,
        additional_body_options={"prompt_cache_key": "caller-key"},
    )

    kwargs = await adapter.build_completion_kwargs(
        adapter.model_provider(), TURN_ONE, top_logprobs=None
    )

    assert kwargs["prompt_cache_key"] == "caller-key"
    assert kwargs["litellm_session_id"] == conversation_affinity_key(TURN_ONE)


def chat_completion_reply(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1759000000,
            "model": "m",
            # Groq's response parser reads service_tier.
            "service_tier": "on_demand",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def anthropic_reply(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    )


@pytest.fixture(autouse=True)
def use_httpx_transport(monkeypatch):
    # LiteLLM sends through aiohttp by default, which respx can't intercept.
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)


async def run_two_turns(
    adapter: LiteLlmAdapter, first_input: str = "What is 2+2?"
) -> list[httpx.Request]:
    route = respx.post(url__regex=r".*").mock(
        side_effect=anthropic_reply
        if adapter.model_provider().name == ModelProviderName.anthropic
        else chat_completion_reply
    )
    first_run = await adapter.invoke(first_input)
    await adapter.invoke("And 3+3?", prior_trace=first_run.trace)
    return [call.request for call in route.calls]


def wire_affinity_values(request: httpx.Request) -> dict[str, str]:
    body = json.loads(request.content)
    values = {
        name: body[name]
        for name in ("prompt_cache_key", "session_id", "litellm_session_id")
        if name in body
    }
    if "x-session-affinity" in request.headers:
        values["x-session-affinity"] = request.headers["x-session-affinity"]
    return values


@pytest.mark.parametrize(
    ("provider_name", "wire_fields"),
    [
        (ModelProviderName.openai, ["prompt_cache_key"]),
        (ModelProviderName.together_ai, ["prompt_cache_key"]),
        (ModelProviderName.openrouter, ["session_id"]),
        (ModelProviderName.fireworks_ai, ["x-session-affinity"]),
        (ModelProviderName.groq, []),
        (ModelProviderName.anthropic, []),
        (ModelProviderName.openai_compatible, []),
    ],
)
@respx.mock
async def test_every_turn_sends_the_same_key_on_the_wire(
    plain_task, provider_name, wire_fields
):
    adapter = make_adapter(plain_task, provider_name)
    if provider_name == ModelProviderName.openai_compatible:
        adapter._api_base = "https://custom.example.com/v1"

    first_request, second_request = await run_two_turns(adapter)

    first_values = wire_affinity_values(first_request)
    assert sorted(first_values) == sorted(wire_fields)
    assert wire_affinity_values(second_request) == first_values


@pytest.mark.parametrize(
    ("provider_name", "wire_field", "shared_between_conversations"),
    [
        (ModelProviderName.openai, "prompt_cache_key", True),
        (ModelProviderName.together_ai, "prompt_cache_key", True),
        (ModelProviderName.openrouter, "session_id", False),
        (ModelProviderName.fireworks_ai, "x-session-affinity", False),
    ],
)
@respx.mock
async def test_conversations_with_one_prompt_share_only_the_prompt_key(
    plain_task, provider_name, wire_field, shared_between_conversations
):
    adapter = make_adapter(plain_task, provider_name)

    first_conversation = await run_two_turns(adapter, "What is 2+2?")
    second_conversation = await run_two_turns(adapter, "Name a color.")

    keys = {
        wire_affinity_values(request)[wire_field]
        for request in first_conversation + second_conversation
    }
    assert len(keys) == (1 if shared_between_conversations else 2)


@respx.mock
async def test_streamed_request_sends_the_key(plain_task):
    adapter = make_adapter(plain_task, ModelProviderName.openai)
    seen_kwargs: list[dict[str, Any]] = []
    original = adapter.build_completion_kwargs

    async def capture(*args: Any, **kwargs: Any) -> dict[str, Any]:
        completion_kwargs = await original(*args, **kwargs)
        seen_kwargs.append(completion_kwargs)
        return completion_kwargs

    stream = adapter.invoke_openai_stream("What is 2+2?")
    with (
        patch.object(adapter, "build_completion_kwargs", side_effect=capture),
        patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            side_effect=RuntimeError("stop after building the request"),
        ),
        pytest.raises(Exception, match="stop after building the request"),
    ):
        async for _ in stream:
            pass

    assert seen_kwargs[0]["prompt_cache_key"] == prompt_affinity_key(
        seen_kwargs[0]["messages"]
    )
