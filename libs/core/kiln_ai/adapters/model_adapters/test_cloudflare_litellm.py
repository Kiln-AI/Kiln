import json
from unittest.mock import patch

import httpx
import litellm
import pytest
import respx

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.errors import KilnRunError, format_error_message
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.retry_classification import (
    is_batch_fatal_error,
    is_retryable_error,
    unwrap_kiln_run_error,
)
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

ACCOUNT_ID = "test-account"
API_KEY = "test-cloudflare-key"
MODEL_ID = "@cf/zai-org/glm-4.7-flash"
CHAT_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1/chat/completions"
)

RATE_LIMIT_BODY = {
    "result": None,
    "success": False,
    "errors": [
        {
            "code": 3021,
            "message": "AiError: AiError: rate limiting: inference request per min rate reached",
        }
    ],
    "messages": [],
}
AUTH_ERROR_BODY = {
    "result": None,
    "success": False,
    "errors": [{"code": 10000, "message": "Authentication error"}],
    "messages": [],
}
SUCCESS_BODY = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1759000000,
    "model": MODEL_ID,
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


@pytest.fixture
def plain_task(tmp_path):
    project = Project(name="Test Project", path=str(tmp_path / "project.kiln"))
    project.save_to_file()
    task = Task(name="Test Task", instruction="Reply with pong", parent=project)
    task.save_to_file()
    return task


@pytest.fixture
def cloudflare_config():
    values = {
        "cloudflare_api_key": API_KEY,
        "cloudflare_account_id": ACCOUNT_ID,
        "cloudflare_ai_gateway_id": None,
    }
    with (
        patch("kiln_ai.adapters.provider_tools.Config") as mock_config,
        patch(
            "kiln_ai.adapters.provider_tools.get_config_value",
            side_effect=lambda key: values.get(key),
        ),
    ):
        for key, value in values.items():
            setattr(mock_config.shared.return_value, key, value)
        yield mock_config.shared.return_value


@pytest.fixture
def make_adapter(plain_task, cloudflare_config):
    def make(gateway_id: str | None):
        cloudflare_config.cloudflare_ai_gateway_id = gateway_id
        return adapter_for_task(
            kiln_task=plain_task,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name=MODEL_ID,
                model_provider_name=ModelProviderName.cloudflare,
                prompt_id="simple_prompt_builder",
                structured_output_mode="default",
            ),
            base_adapter_config=AdapterConfig(allow_saving=False),
        )

    return make


async def invoke_with_error(adapter) -> KilnRunError:
    with pytest.raises(KilnRunError) as exc_info:
        await adapter.invoke("ping")
    return exc_info.value


@pytest.mark.asyncio
@respx.mock
async def test_cloudflare_request_wiring_through_gateway(make_adapter):
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=SUCCESS_BODY)
    )
    adapter = make_adapter("my-gateway")

    run = await adapter.invoke("ping")

    assert run.output.output == "pong"
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["cf-aig-gateway-id"] == "my-gateway"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content)["model"] == MODEL_ID


@pytest.mark.asyncio
@respx.mock
async def test_cloudflare_request_without_gateway_omits_header(make_adapter):
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=SUCCESS_BODY)
    )
    adapter = make_adapter(None)

    await adapter.invoke("ping")

    assert "cf-aig-gateway-id" not in route.calls.last.request.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("gateway_id", [None, "my-gateway"])
@respx.mock
async def test_cloudflare_rate_limit_is_retryable_rate_limit_error(
    make_adapter, gateway_id
):
    respx.post(CHAT_URL).mock(return_value=httpx.Response(429, json=RATE_LIMIT_BODY))

    error = await invoke_with_error(make_adapter(gateway_id))

    original = unwrap_kiln_run_error(error)
    assert isinstance(original, litellm.RateLimitError)
    assert is_retryable_error(error)
    assert not is_batch_fatal_error(error)
    assert format_error_message(original).startswith("Rate limit exceeded")


@pytest.mark.asyncio
@respx.mock
async def test_cloudflare_auth_error_is_batch_fatal(make_adapter):
    respx.post(CHAT_URL).mock(return_value=httpx.Response(401, json=AUTH_ERROR_BODY))

    error = await invoke_with_error(make_adapter(None))

    assert isinstance(unwrap_kiln_run_error(error), litellm.AuthenticationError)
    assert not is_retryable_error(error)
    assert is_batch_fatal_error(error)
