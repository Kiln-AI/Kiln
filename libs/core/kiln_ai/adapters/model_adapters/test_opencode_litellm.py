import json
from typing import Any

import httpx
import litellm
import pytest
import respx

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.retry_classification import (
    is_batch_fatal_error,
    is_retryable_error,
    unwrap_kiln_run_error,
)
from kiln_ai.datamodel import Project, Task, TaskRun
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.utils.config import Config

API_KEY = "oc_sk_test"
MODEL_ID = "claude-haiku-5-5"
CHAT_URL = "https://opencode.ai/inference/openai/v1/chat/completions"
REPORTED_COST = 0.00113
TOKENS = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}

# Error bodies recorded from OpenCode. The 402 body follows OpenCode's billing docs,
# since an out-of-credits workspace can't be reproduced on demand.
ERROR_CASES = [
    pytest.param(
        402,
        {
            "error": {
                "type": "server_error",
                "message": "Upstream request failed: Insufficient account funds",
            }
        },
        id="out_of_credits_402",
    ),
    pytest.param(
        403,
        {
            "error": {
                "type": "permission_error",
                "message": "Model access is disabled. Change model access at https://opencode.ai/console/org_123/models.",
            }
        },
        id="model_disabled_403",
    ),
    pytest.param(
        410,
        {
            "type": "error",
            "error": {
                "type": "ModelDeprecated",
                "message": "Model glm-5.2 has been deprecated. Use glm-5.3 instead.",
            },
            "metadata": {"model": "glm-5.2", "replacement": "glm-5.3"},
        },
        id="model_retired_410",
    ),
    pytest.param(
        400,
        {
            "error": {
                "type": "server_error",
                "message": "Upstream request failed: Model is unavailable.",
            }
        },
        id="unknown_model_400",
    ),
    pytest.param(
        429,
        {
            "type": "error",
            "error": {
                "type": "FreeUsageLimitError",
                "message": "Free usage limit reached. Free models work in OpenCode only.",
            },
        },
        id="free_model_429",
    ),
]


def completion_body(model: str, usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1763800000,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


def streamed_completion(model: str, usage: dict[str, Any]) -> httpx.Response:
    base = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1763800000,
        "model": model,
    }
    chunks = [
        {
            **base,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "pong"},
                    "finish_reason": None,
                }
            ],
        },
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {**base, "choices": [], "usage": usage},
    ]
    sse = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    sse += "data: [DONE]\n\n"
    return httpx.Response(
        200, content=sse.encode(), headers={"content-type": "text/event-stream"}
    )


def reply(streaming: bool, usage: dict[str, Any], model: str = MODEL_ID):
    if streaming:
        return streamed_completion(model, usage)
    return httpx.Response(200, json=completion_body(model, usage))


async def run_task(adapter: BaseAdapter, streaming: bool) -> TaskRun:
    if not streaming:
        return await adapter.invoke("ping")
    stream = adapter.invoke_openai_stream("ping")
    async for _ in stream:
        pass
    return stream.task_run


@pytest.fixture(autouse=True)
def use_httpx_transport(monkeypatch):
    # LiteLLM sends through aiohttp by default, which respx can't intercept.
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)


@pytest.fixture(autouse=True)
def opencode_key():
    Config.shared().opencode_api_key = API_KEY


@pytest.fixture
def plain_task(tmp_path):
    project = Project(name="Test Project", path=str(tmp_path / "project.kiln"))
    project.save_to_file()
    task = Task(name="Test Task", instruction="Reply with pong", parent=project)
    task.save_to_file()
    return task


@pytest.fixture
def make_adapter(plain_task):
    def make(model_id: str = MODEL_ID) -> BaseAdapter:
        return adapter_for_task(
            kiln_task=plain_task,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name=model_id,
                model_provider_name=ModelProviderName.opencode,
                prompt_id="simple_prompt_builder",
                structured_output_mode="default",
            ),
            base_adapter_config=AdapterConfig(allow_saving=False),
        )

    return make


streaming_modes = pytest.mark.parametrize(
    "streaming", [False, True], ids=["non_streaming", "streaming"]
)


@pytest.mark.asyncio
@respx.mock
async def test_opencode_request_wiring(make_adapter):
    route = respx.post(CHAT_URL).mock(
        return_value=reply(False, {**TOKENS, "cost": REPORTED_COST})
    )

    run = await make_adapter().invoke("ping")

    assert run.output.output == "pong"
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content)["model"] == MODEL_ID


@pytest.mark.asyncio
@streaming_modes
@respx.mock
async def test_opencode_cost_from_usage_cost(make_adapter, streaming):
    respx.post(CHAT_URL).mock(
        return_value=reply(streaming, {**TOKENS, "cost": REPORTED_COST})
    )

    run = await run_task(make_adapter(), streaming)

    assert run.usage is not None
    assert run.usage.cost == REPORTED_COST
    assert run.usage.input_tokens == TOKENS["prompt_tokens"]


@pytest.mark.asyncio
@streaming_modes
@respx.mock
async def test_opencode_cost_ignores_litellm_price_list(make_adapter, streaming):
    model = "gpt-4o-mini"
    litellm_cost = sum(
        litellm.cost_per_token(
            model=model,
            prompt_tokens=TOKENS["prompt_tokens"],
            completion_tokens=TOKENS["completion_tokens"],
        )
    )
    assert litellm_cost > 0 and litellm_cost != REPORTED_COST
    respx.post(CHAT_URL).mock(
        return_value=reply(streaming, {**TOKENS, "cost": REPORTED_COST}, model=model)
    )

    run = await run_task(make_adapter(model), streaming)

    assert run.usage is not None
    assert run.usage.cost == REPORTED_COST


@pytest.mark.asyncio
@streaming_modes
@respx.mock
async def test_opencode_missing_usage_cost_records_no_cost(make_adapter, streaming):
    respx.post(CHAT_URL).mock(
        return_value=reply(streaming, TOKENS, model="gpt-4o-mini")
    )

    run = await run_task(make_adapter("gpt-4o-mini"), streaming)

    assert run.usage is not None
    assert run.usage.input_tokens == TOKENS["prompt_tokens"]
    assert run.usage.cost is None


@pytest.mark.asyncio
@respx.mock
async def test_opencode_int_zero_cost_recorded_as_float(make_adapter):
    respx.post(CHAT_URL).mock(return_value=reply(False, {**TOKENS, "cost": 0}))

    run = await make_adapter().invoke("ping")

    assert run.usage is not None
    assert run.usage.cost == 0.0
    assert isinstance(run.usage.cost, float)


async def kept_exception(adapter: BaseAdapter, streaming: bool) -> Exception:
    """The exception Kiln keeps for a failed run: the KilnRunError's original when
    non-streaming, the raised exception itself when streaming."""
    if not streaming:
        with pytest.raises(KilnRunError) as run_error:
            await adapter.invoke("ping")
        return unwrap_kiln_run_error(run_error.value)
    with pytest.raises(Exception) as stream_error:
        await run_task(adapter, streaming=True)
    assert not isinstance(stream_error.value, KilnRunError)
    return stream_error.value


@pytest.mark.asyncio
@streaming_modes
@pytest.mark.parametrize("status_code,body", ERROR_CASES)
@respx.mock
async def test_opencode_error_text_kept(make_adapter, streaming, status_code, body):
    respx.post(CHAT_URL).mock(return_value=httpx.Response(status_code, json=body))

    error = await kept_exception(make_adapter(), streaming)

    assert body["error"]["message"] in str(error)
    assert getattr(error, "status_code", None) == status_code


@pytest.mark.asyncio
@streaming_modes
@respx.mock
async def test_opencode_auth_error_is_batch_fatal(make_adapter, streaming):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            401,
            json={"error": {"type": "authentication_error", "message": "Invalid key"}},
        )
    )

    error = await kept_exception(make_adapter(), streaming)

    assert isinstance(error, litellm.AuthenticationError)
    assert "Invalid key" in str(error)
    assert getattr(error, "status_code", None) == 401
    assert is_batch_fatal_error(error)
    assert not is_retryable_error(error)


@pytest.mark.asyncio
@streaming_modes
@respx.mock
async def test_opencode_rate_limit_is_retryable(make_adapter, streaming):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            429,
            json={"error": {"type": "rate_limit_error", "message": "Rate limited"}},
        )
    )

    error = await kept_exception(make_adapter(), streaming)

    assert isinstance(error, litellm.RateLimitError)
    assert "Rate limited" in str(error)
    assert getattr(error, "status_code", None) == 429
    assert is_retryable_error(error)
    assert not is_batch_fatal_error(error)
