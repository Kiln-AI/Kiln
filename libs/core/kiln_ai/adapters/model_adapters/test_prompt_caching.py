import asyncio
import json
import random

import pytest

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.test_paid_utils import (
    skip_if_missing_provider_keys,
)
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

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
            "minimax_m2_5",
            id="together_ai/minimax_m2_5",
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
