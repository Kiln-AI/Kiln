import json

import httpx
import litellm
import pytest
import respx

from kiln_ai.adapters.ml_model_list import ModelName, ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    OpenRouterRouting,
)

API_KEY = "test-openrouter-key"
BASE_URL = "https://openrouter.ai/api/v1"
CHAT_URL = f"{BASE_URL}/chat/completions"
DEFAULT_ORDER = [
    "fireworks",
    "parasail",
    "together",
    "deepinfra",
    "novita",
    "groq",
    "amazon-bedrock",
    "azure",
    "nebius",
]
SUCCESS_BODY = {
    "id": "gen-test",
    "object": "chat.completion",
    "created": 1759000000,
    "model": "openai/gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "pong"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
}


@pytest.fixture(autouse=True)
def use_httpx_transport(monkeypatch):
    # LiteLLM sends through aiohttp by default, which respx can't intercept.
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)


@pytest.fixture(autouse=True)
def fake_openrouter_key(monkeypatch):
    # The adapter checks that an OpenRouter key is configured before a call. CI has
    # none, and a real key from a local .env must not reach the test.
    monkeypatch.setenv("OPENROUTER_API_KEY", API_KEY)


@pytest.fixture
def plain_task(tmp_path):
    project = Project(name="Test Project", path=str(tmp_path / "project.kiln"))
    project.save_to_file()
    task = Task(name="Test Task", instruction="Reply with pong", parent=project)
    task.save_to_file()
    return task


@pytest.fixture
def make_adapter(plain_task):
    def make(
        routing: OpenRouterRouting | None,
        provider: ModelProviderName = ModelProviderName.openrouter,
    ) -> LiteLlmAdapter:
        run_config = KilnAgentRunConfigProperties(
            model_name=ModelName.gpt_4o_mini,
            model_provider_name=ModelProviderName.openrouter,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            openrouter_routing=routing,
        )
        # model_copy skips validation, the way callers that copy a run config and
        # change one field do, so the adapter's own check is the one under test.
        run_config = run_config.model_copy(update={"model_provider_name": provider})
        return LiteLlmAdapter(
            config=LiteLlmConfig(
                run_config_properties=run_config,
                base_url=BASE_URL,
                additional_body_options={"api_key": API_KEY},
            ),
            kiln_task=plain_task,
            base_adapter_config=AdapterConfig(allow_saving=False),
        )

    return make


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "routing,expected_provider",
    [
        (None, {"order": DEFAULT_ORDER}),
        (
            OpenRouterRouting(zero_data_retention=True),
            {"order": DEFAULT_ORDER, "zdr": True},
        ),
        (
            OpenRouterRouting(zero_data_retention=True, sort="price"),
            {"sort": "price", "zdr": True},
        ),
    ],
)
async def test_openrouter_request_body_provider_object(
    make_adapter, routing, expected_provider
):
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=SUCCESS_BODY)
    )

    run = await make_adapter(routing).invoke("ping")

    assert run.output.output == "pong"
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content)["provider"] == expected_provider


@pytest.mark.asyncio
@respx.mock
async def test_zero_data_retention_off_openrouter_sends_no_request(make_adapter):
    any_request = respx.route().mock(
        return_value=httpx.Response(200, json=SUCCESS_BODY)
    )

    with pytest.raises(ValueError, match="zero data retention"):
        make_adapter(
            OpenRouterRouting(zero_data_retention=True), ModelProviderName.openai
        )

    assert any_request.call_count == 0
