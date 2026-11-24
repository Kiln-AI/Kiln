"""Offline wire tests for the run config's optional model settings.

These run real LiteLLM through LiteLlmAdapter, with respx standing in for the
provider, so they show what reaches the wire once LiteLLM has translated each
setting or dropped it for a model that does not accept it.
"""

import json
from typing import Any

import httpx
import litellm
import pytest
import respx

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelName, ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.utils.config import Config

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

OPENAI_REPLY = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1759000000,
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "4"},
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}
ANTHROPIC_REPLY = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250929",
    "content": [{"type": "text", "text": "4"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 5},
}

ALL_SETTINGS = {
    "max_output_tokens": 256,
    "seed": 7,
    "frequency_penalty": 0.5,
    "presence_penalty": 0.25,
}
# Every name a setting can take in a request body, in any provider's format.
SETTING_BODY_KEYS = {
    "max_tokens",
    "max_completion_tokens",
    "seed",
    "frequency_penalty",
    "presence_penalty",
}


@pytest.fixture(autouse=True)
def use_httpx_transport(monkeypatch):
    # LiteLLM sends through aiohttp by default, which respx can't intercept.
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)


@pytest.fixture(autouse=True)
def provider_keys():
    Config.shared().open_ai_api_key = "sk-test-openai-key"
    Config.shared().anthropic_api_key = "sk-test-anthropic-key"


@pytest.fixture
def plain_task(tmp_path):
    project = Project(name="Test Project", path=str(tmp_path / "project.kiln"))
    project.save_to_file()
    task = Task(name="Test Task", instruction="Answer briefly", parent=project)
    task.save_to_file()
    return task


async def sent_settings(
    task: Task,
    provider: ModelProviderName,
    model_name: str,
    url: str,
    reply: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Runs the task once and returns the settings found in the request body."""
    route = respx.post(url).mock(return_value=httpx.Response(200, json=reply))
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            **settings,
        ),
        base_adapter_config=AdapterConfig(allow_saving=False),
    )

    run = await adapter.invoke("what is 2+2")

    assert run.output.output == "4"
    body = json.loads(route.calls[0].request.content)
    return {key: body[key] for key in SETTING_BODY_KEYS if key in body}


@respx.mock
async def test_model_that_accepts_every_setting_gets_them_all(plain_task):
    sent = await sent_settings(
        plain_task,
        ModelProviderName.openai,
        ModelName.gpt_4o,
        OPENAI_URL,
        OPENAI_REPLY,
        ALL_SETTINGS,
    )

    assert sent == {
        "max_tokens": 256,
        "seed": 7,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.25,
    }


@respx.mock
async def test_settings_a_model_does_not_accept_are_dropped(plain_task):
    # Anthropic's Messages API has no seed and no penalties.
    sent = await sent_settings(
        plain_task,
        ModelProviderName.anthropic,
        ModelName.claude_sonnet_4_5,
        ANTHROPIC_URL,
        ANTHROPIC_REPLY,
        ALL_SETTINGS,
    )

    assert sent == {"max_tokens": 256}


@respx.mock
async def test_unset_settings_send_nothing(plain_task):
    sent = await sent_settings(
        plain_task,
        ModelProviderName.openai,
        ModelName.gpt_4o,
        OPENAI_URL,
        OPENAI_REPLY,
        {},
    )

    assert sent == {}
