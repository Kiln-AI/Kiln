import asyncio
import json
import random
import re

import httpx
import litellm
import pytest
import respx

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    prompt_cache_injection_points,
)
from kiln_ai.adapters.model_adapters.test_paid_utils import (
    skip_if_missing_provider_keys,
)
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.utils.config import Config

# Repeated to exceed minimum token thresholds for cache eligibility (e.g. 1024 tokens for Anthropic)
CACHE_SEED_SYSTEM_PROMPT = ("You are a helpful assistant. " * 1000).strip()


def build_caching_test_task(tmp_path) -> Task:
    project = Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()
    task = Task(
        parent=project,
        name="caching test",
        instruction=CACHE_SEED_SYSTEM_PROMPT,
    )
    task.save_to_file()
    return task


@pytest.mark.paid
@pytest.mark.prerelease
@pytest.mark.parametrize(
    ("provider_name", "model_name"),
    [
        pytest.param(
            ModelProviderName.anthropic,
            "claude_opus_4_6",
            id="anthropic/claude_opus_4_6",
        ),
        pytest.param(
            ModelProviderName.anthropic,
            "claude_sonnet_4_6",
            id="anthropic/claude_sonnet_4_6",
        ),
        pytest.param(
            ModelProviderName.openai,
            "gpt_5_4_mini",
            id="openai/gpt_5_4_mini",
        ),
        pytest.param(
            ModelProviderName.openrouter,
            "gpt_5_4_mini",
            id="openrouter/gpt_5_4_mini",
        ),
        pytest.param(
            ModelProviderName.gemini_api,
            "gemini_3_flash",
            id="gemini_api/gemini_3_flash",
        ),
        pytest.param(
            ModelProviderName.fireworks_ai,
            "qwen_3p6_plus",
            id="fireworks_ai/qwen_3p6_plus",
        ),
        pytest.param(
            ModelProviderName.together_ai,
            "minimax_m2_7",
            id="together_ai/minimax_m2_7",
        ),
    ],
)
async def test_prompt_caching_cache_hit(
    tmp_path, test_output_dir, provider_name, model_name
):
    skip_if_missing_provider_keys(provider_name)

    task = build_caching_test_task(tmp_path)

    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_instructions,
            temperature=1,
        ),
        base_adapter_config=AdapterConfig(automatic_prompt_caching=True),
    )

    # First call seeds the cache
    run1 = await adapter.invoke("What is 2+2?")

    # sleep for 10 seconds (async)
    await asyncio.sleep(10)

    trace = run1.trace
    has_cached_tokens_at_least_once = False
    log_path = test_output_dir / "prompt_caching_cache_hit.log"
    for i in range(10):
        lines: list[str] = [f"Request #{i}...\n"]
        rand_num = random.randint(0, 100)
        run2 = await adapter.invoke(f"What is 3 + {rand_num}?", prior_trace=trace)
        trace = run2.trace
        if (
            run2.usage is not None
            and run2.usage.cached_tokens is not None
            and run2.usage.cached_tokens > 0
        ):
            has_cached_tokens_at_least_once = True
            lines.append(f"Cached tokens found for request #{i}\n")
            lines.append(
                f"Usage: {json.dumps(run2.usage.model_dump(mode='json'), indent=2)}\n"
            )
        else:
            lines.append(f"No cached tokens found for request #{i}\n")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.writelines(lines)
        await asyncio.sleep(10)

    assert has_cached_tokens_at_least_once


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL_ID = "claude-sonnet-4-5-20250929"
GEMINI_GENERATE_URL = re.compile(
    r"https://generativelanguage\.googleapis\.com/.*:generateContent"
)
EPHEMERAL = {"type": "ephemeral"}
SYSTEM_MARK = {"location": "message", "index": 0}
LAST_MESSAGE_MARK = {"location": "message", "index": -1}

UNCACHED_INPUT_TOKENS = 12
SYSTEM_PROMPT_TOKENS = 2400
OUTPUT_TOKENS = 5


def anthropic_reply(cache_usage: dict[str, int]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": ANTHROPIC_MODEL_ID,
            "content": [{"type": "text", "text": "4"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": UNCACHED_INPUT_TOKENS,
                "output_tokens": OUTPUT_TOKENS,
                **cache_usage,
            },
        },
    )


CACHE_WRITE = {
    "cache_creation_input_tokens": SYSTEM_PROMPT_TOKENS,
    "cache_read_input_tokens": 0,
}
CACHE_READ = {
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": SYSTEM_PROMPT_TOKENS,
}


def gemini_reply() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": "Adding the numbers.", "thought": True},
                            {"text": "4"},
                        ],
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 1,
                "totalTokenCount": 11,
            },
        },
    )


def offline_adapter(
    task: Task,
    provider_name: ModelProviderName,
    model_name: str,
    automatic_prompt_caching: bool,
) -> BaseAdapter:
    return adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
        base_adapter_config=AdapterConfig(
            allow_saving=False, automatic_prompt_caching=automatic_prompt_caching
        ),
    )


def request_bodies(route: respx.Route) -> list[dict]:
    return [json.loads(call.request.content) for call in route.calls]


@pytest.fixture
def offline_task(tmp_path, monkeypatch) -> Task:
    """A long-prompt task whose model calls can only reach respx routes."""
    # LiteLLM sends through aiohttp by default, which respx can't intercept.
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    Config.shared().anthropic_api_key = "sk-ant-test-key"
    Config.shared().gemini_api_key = "test-gemini-key"
    return build_caching_test_task(tmp_path)


ONE_SHOT_MESSAGES = [
    {"role": "system", "content": "instructions"},
    {"role": "user", "content": "hi"},
]
SECOND_TURN_MESSAGES = [
    *ONE_SHOT_MESSAGES,
    {"role": "assistant", "content": "hello"},
    {"role": "user", "content": "and now?"},
]


@pytest.mark.parametrize(
    ("litellm_model_id", "messages", "expects_later_call", "expected_points"),
    [
        pytest.param(model_id, ONE_SHOT_MESSAGES, False, [SYSTEM_MARK], id=model_id)
        for model_id in (
            "anthropic/claude-sonnet-4-5-20250929",
            "openrouter/anthropic/claude-sonnet-4.5",
            "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "vertex_ai/claude-sonnet-4-5@20250929",
        )
    ]
    + [
        pytest.param(model_id, ONE_SHOT_MESSAGES, False, [], id=model_id)
        for model_id in (
            "openai/gpt-5-mini",
            "gemini/gemini-2.5-flash",
            "openrouter/google/gemini-2.5-flash",
            "fireworks_ai/accounts/fireworks/models/qwen3-235b-a22b",
        )
    ]
    + [
        pytest.param(
            "anthropic/claude-sonnet-4-5-20250929",
            ONE_SHOT_MESSAGES,
            True,
            [SYSTEM_MARK, LAST_MESSAGE_MARK],
            id="claude_later_call_expected",
        ),
        pytest.param(
            "anthropic/claude-sonnet-4-5-20250929",
            SECOND_TURN_MESSAGES,
            False,
            [SYSTEM_MARK, LAST_MESSAGE_MARK],
            id="claude_messages_hold_a_model_reply",
        ),
        pytest.param(
            "anthropic/claude-sonnet-4-5-20250929",
            ONE_SHOT_MESSAGES[1:],
            False,
            [],
            id="claude_without_system_prompt",
        ),
        pytest.param(
            "gemini/gemini-2.5-flash",
            SECOND_TURN_MESSAGES,
            False,
            [LAST_MESSAGE_MARK],
            id="gemini_messages_hold_a_model_reply",
        ),
    ],
)
def test_prompt_cache_injection_points(
    litellm_model_id, messages, expects_later_call, expected_points
):
    points = prompt_cache_injection_points(
        litellm_model_id, messages, expects_later_call
    )
    assert points == expected_points


@respx.mock
async def test_single_turn_claude_run_caches_system_prompt(offline_task):
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[anthropic_reply(CACHE_WRITE), anthropic_reply(CACHE_READ)]
    )
    adapter = offline_adapter(
        offline_task, ModelProviderName.anthropic, "claude_sonnet_4_5", True
    )

    cold_run = await adapter.invoke("What is 2+2?")
    warm_run = await adapter.invoke("What is 3+3?")

    for body in request_bodies(route):
        assert body["system"][-1]["cache_control"] == EPHEMERAL
        # Nothing re-sends the user message of a one-shot run, so it is not cached.
        assert "cache_control" not in json.dumps(body["messages"])

    rates = litellm.model_cost[ANTHROPIC_MODEL_ID]
    fixed_cost = (
        UNCACHED_INPUT_TOKENS * rates["input_cost_per_token"]
        + OUTPUT_TOKENS * rates["output_cost_per_token"]
    )
    assert cold_run.usage is not None and warm_run.usage is not None
    for usage in (cold_run.usage, warm_run.usage):
        assert usage.input_tokens == UNCACHED_INPUT_TOKENS + SYSTEM_PROMPT_TOKENS
    assert cold_run.usage.cached_tokens == 0
    assert cold_run.usage.cache_write_tokens == SYSTEM_PROMPT_TOKENS
    assert cold_run.usage.cost == pytest.approx(
        fixed_cost + SYSTEM_PROMPT_TOKENS * rates["cache_creation_input_token_cost"]
    )
    assert warm_run.usage.cached_tokens == SYSTEM_PROMPT_TOKENS
    assert warm_run.usage.cache_write_tokens == 0
    assert warm_run.usage.cost == pytest.approx(
        fixed_cost + SYSTEM_PROMPT_TOKENS * rates["cache_read_input_token_cost"]
    )


@respx.mock
async def test_multi_turn_claude_run_marks_system_prompt_and_new_turn(offline_task):
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[anthropic_reply(CACHE_WRITE), anthropic_reply(CACHE_READ)]
    )
    adapter = offline_adapter(
        offline_task, ModelProviderName.anthropic, "claude_sonnet_4_5", True
    )

    first_turn = await adapter.invoke("What is 2+2?")
    await adapter.invoke("What is 3+3?", prior_trace=first_turn.trace)

    second_request = request_bodies(route)[1]
    assert second_request["system"][-1]["cache_control"] == EPHEMERAL
    marked_messages = [
        message["content"][-1]["text"]
        for message in second_request["messages"]
        if isinstance(message["content"], list)
        and "cache_control" in message["content"][-1]
    ]
    assert marked_messages == ["What is 3+3?"]


@respx.mock
async def test_claude_run_without_caching_sends_no_cache_marks(offline_task):
    route = respx.post(ANTHROPIC_URL).mock(return_value=anthropic_reply({}))
    adapter = offline_adapter(
        offline_task, ModelProviderName.anthropic, "claude_sonnet_4_5", False
    )

    await adapter.invoke("What is 2+2?")

    assert b"cache_control" not in route.calls.last.request.content


@respx.mock
async def test_gemini_request_is_the_same_with_and_without_caching(offline_task):
    # Only generateContent is routed, so a call to Gemini's cachedContents API fails.
    route = respx.post(GEMINI_GENERATE_URL).mock(return_value=gemini_reply())

    for automatic_prompt_caching in (False, True):
        adapter = offline_adapter(
            offline_task,
            ModelProviderName.gemini_api,
            "gemini_2_5_flash",
            automatic_prompt_caching,
        )
        await adapter.invoke("What is 2+2?")

    without_caching, with_caching = request_bodies(route)
    assert with_caching == without_caching
