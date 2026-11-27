"""Offline wire tests for the run config's optional model settings.

These run real LiteLLM through LiteLlmAdapter, with respx standing in for the
provider, so they show what reaches the wire once LiteLLM has translated each
setting or dropped it for a model that does not accept it.
"""

import json

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

ENDPOINTS = {
    ModelProviderName.openai: (OPENAI_URL, OPENAI_REPLY),
    ModelProviderName.anthropic: (ANTHROPIC_URL, ANTHROPIC_REPLY),
}

ALL_SETTINGS = {
    "max_output_tokens": 256,
    "seed": 7,
    "frequency_penalty": 0.5,
    "presence_penalty": 0.25,
}
# The names the settings take in an OpenAI or Anthropic request body.
SETTING_BODY_KEYS = {
    "max_tokens",
    "max_completion_tokens",
    "max_output_tokens",
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


@respx.mock
@pytest.mark.parametrize(
    "provider,model_name,run_config,expected",
    [
        pytest.param(
            ModelProviderName.openai,
            ModelName.gpt_4o,
            ALL_SETTINGS,
            {
                "max_tokens": 256,
                "seed": 7,
                "frequency_penalty": 0.5,
                "presence_penalty": 0.25,
            },
            id="model_that_accepts_every_setting",
        ),
        pytest.param(
            ModelProviderName.openai,
            ModelName.gpt_5,
            ALL_SETTINGS,
            {"max_completion_tokens": 256, "seed": 7},
            id="reasoning_model_renames_limit_and_drops_penalties",
        ),
        pytest.param(
            ModelProviderName.anthropic,
            ModelName.claude_sonnet_4_5,
            # Thinking is off: Anthropic rejects a max_tokens that is not above the
            # thinking budget, and this model thinks by default.
            {**ALL_SETTINGS, "thinking_level": "none"},
            {"max_tokens": 256},
            id="anthropic_drops_seed_and_penalties",
        ),
        pytest.param(
            ModelProviderName.openai,
            ModelName.gpt_4o,
            {},
            {},
            id="unset_settings_send_nothing",
        ),
    ],
)
async def test_settings_in_request_body(
    plain_task, provider, model_name, run_config, expected
):
    url, reply = ENDPOINTS[provider]
    route = respx.post(url).mock(return_value=httpx.Response(200, json=reply))
    adapter = adapter_for_task(
        plain_task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            **run_config,
        ),
        base_adapter_config=AdapterConfig(allow_saving=False),
    )

    run = await adapter.invoke("what is 2+2")

    assert run.output.output == "4"
    [call] = route.calls
    body = json.loads(call.request.content)
    assert "thinking" not in body
    assert {key: body[key] for key in SETTING_BODY_KEYS if key in body} == expected
