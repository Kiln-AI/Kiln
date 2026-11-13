import dataclasses
from pathlib import Path

import pytest

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.adapter_registry import (
    adapter_for_task,
    litellm_core_provider_config,
)
from kiln_ai.adapters.eval.eval_utils.eval_trace_formatter import EvalTraceFormatter
from kiln_ai.adapters.ml_model_list import (
    ModelName,
    ModelProviderName,
    built_in_models,
)
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.test_paid_utils import (
    skip_if_missing_provider_keys,
)
from kiln_ai.adapters.pytest_prerelease_whitelist import PRERELEASE_THINKING_MODELS
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

# Anthropic's adaptive-thinking models (Opus 4.6+) decide per request whether to emit
# a thinking block, and Opus 4.7/4.8 return encrypted thinking (a signature with no
# plaintext) even on the raw Anthropic API. So a non-"none" thinking level is not
# guaranteed to surface reasoning content for these models on the native Anthropic
# provider; for them we only assert the run succeeded. OpenRouter still exposes
# reasoning for the same models, so it is not relaxed.
ANTHROPIC_ADAPTIVE_THINKING_MODELS = {
    ModelName.claude_opus_4_6.value,
    ModelName.claude_opus_4_7.value,
    ModelName.claude_opus_4_8.value,
    ModelName.claude_sonnet_4_6.value,
    ModelName.claude_sonnet_5.value,
    ModelName.claude_sonnet_5_5.value,
}

# Claude Sonnet 5.5 recalibrated its effort levels: at low and medium it skips thinking
# entirely on simple prompts (the response carries no thinking block at all, on the raw
# Anthropic API as well). That decision is made by the model, not the gateway, so
# OpenRouter has nothing to surface either; for it we only assert the run succeeded
# on OpenRouter too.
CLAUDE_SKIPS_THINKING_ON_OPENROUTER_MODELS = {
    ModelName.claude_sonnet_5_5.value,
}

# Gemini 3.x Flash models use adaptive reasoning: they decide per request whether to
# emit a thinking channel, so a non-"none" thinking level is not guaranteed to surface
# reasoning content. This is worse at low thinking budgets and on the native gemini_api
# provider, so for these models on any Gemini provider we only assert the run succeeded.
GEMINI_ADAPTIVE_THINKING_MODELS = {
    ModelName.gemini_3_flash.value,
    ModelName.gemini_3_5_flash.value,
    ModelName.gemini_3_6_flash.value,
    ModelName.gemini_3_8_flash.value,
    ModelName.gemini_3_5_flash_lite.value,
    # On gemini_api, Gemini 4 Argon returns no reasoning at low or medium.
    ModelName.gemini_4_argon.value,
}


LOGIC_PUZZLE_PROMPT = "Four people-A, B, C, and D-each have a different favorite color (red, blue, green, yellow) and a different pet (cat, dog, fish, bird). Use the clues to determine each person's color and pet.\n\n1) A does not like red or blue.\n2) The bird's owner likes yellow.\n3) B likes green.\n4) The dog is owned by the person who likes blue.\n5) C does not own the fish.\n6) D likes red.\n\nQuestion: Who owns the fish, and what color do they like? Answer with just: \"<person>, <color>\"."


def build_thinking_level_test_task(tmp_path: Path) -> datamodel.Task:
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are a calculator. Return the final answer only.",
    )
    task.save_to_file()
    return task


def get_models_for_provider(provider_name: str) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    for model in built_in_models:
        for provider in model.providers:
            if provider.name != provider_name:
                continue
            if not provider.model_id:
                continue
            if not provider.available_thinking_levels:
                continue
            for level in provider.available_thinking_levels.values():
                params.append((model.name, level))
    return params


def reasoning_content_from_run(run: datamodel.TaskRun) -> str | None:
    """Get the reasoning content from the run. This is the content that the model used to generate the output."""
    if run.intermediate_outputs is not None:
        reasoning = run.intermediate_outputs.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()

    if run.trace:
        for message in run.trace:
            if not isinstance(message, dict):
                continue
            reasoning = EvalTraceFormatter.reasoning_content_from_message(message)
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning.strip()

    return None


def get_all_model_providers_with_thinking_levels(
    provider_names: list[ModelProviderName],
) -> list[object]:
    params: list[object] = []
    for provider_name in provider_names:
        for model_name, thinking_level in get_models_for_provider(provider_name):
            case_id = f"{provider_name}/{model_name}/{thinking_level}"
            params.append(
                pytest.param(provider_name, model_name, thinking_level, id=case_id)
            )
    return params


@pytest.mark.paid
@pytest.mark.parametrize(
    ("provider_name", "model_name", "thinking_level"),
    get_all_model_providers_with_thinking_levels(
        [
            ModelProviderName.openrouter,
            ModelProviderName.openai,
            ModelProviderName.anthropic,
            ModelProviderName.gemini_api,
            ModelProviderName.cloudflare,
        ]
    ),
)
async def test_thinking_level_reasoning_content(
    tmp_path, provider_name: str, model_name: str, thinking_level: str
):
    skip_if_missing_provider_keys(provider_name)
    # Anthropic requires temperature 1 with thinking on, and GPT-6 rejects any other
    # value. 1 is Kiln's default, so every model in the catalog accepts it.
    temperature = 1

    task = build_thinking_level_test_task(tmp_path)
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            thinking_level=thinking_level,
            temperature=temperature,
            top_p=1,
        ),
    )
    run = await adapter.invoke(LOGIC_PUZZLE_PROMPT)
    reasoning_content = reasoning_content_from_run(run)
    if thinking_level == "none":
        assert reasoning_content is None, (
            f"Expected no reasoning content for thinking_level='none', "
            f"but got {len(reasoning_content)} chars "
            f"(provider={provider_name}, model={model_name})"
        )
    elif provider_name == ModelProviderName.openai:
        # OpenAI returns reasoning only as a summary, which Kiln requests only when the
        # user turns on reasoning summaries (off here). Reaching here means the run
        # succeeded; test_openai_reasoning_summaries_paid covers summaries.
        pass
    elif (
        provider_name == ModelProviderName.anthropic
        and model_name in ANTHROPIC_ADAPTIVE_THINKING_MODELS
    ):
        # Adaptive/encrypted-thinking models may not surface reasoning content (see
        # note above); reaching here means the run succeeded, which is what we verify.
        pass
    elif (
        provider_name == ModelProviderName.openrouter
        and model_name in CLAUDE_SKIPS_THINKING_ON_OPENROUTER_MODELS
    ):
        # See note above: the model skips thinking at lower effort levels regardless of
        # gateway; reaching here means the run succeeded, which is what we verify.
        pass
    elif (
        provider_name
        in (
            ModelProviderName.gemini_api,
            ModelProviderName.openrouter,
            ModelProviderName.vertex,
        )
        and model_name in GEMINI_ADAPTIVE_THINKING_MODELS
    ):
        # Adaptive-reasoning Gemini models may not surface reasoning content (see note
        # above); reaching here means the run succeeded, which is what we verify.
        pass
    else:
        assert reasoning_content is not None, (
            f"Expected reasoning content for thinking_level='{thinking_level}', "
            f"but got None "
            f"(provider={provider_name}, model={model_name})"
        )


def openai_reasoning_summary_models() -> list[str]:
    return [
        model.name
        for model in built_in_models
        for provider in model.providers
        if provider.name == ModelProviderName.openai
        and provider.openai_reasoning_summary is not None
    ]


# Needs an OpenAI organization that is verified for reasoning summaries; unverified
# organizations get a 400 on every case.
@pytest.mark.paid
@pytest.mark.parametrize("streamed", [False, True], ids=["invoke", "openai_stream"])
@pytest.mark.parametrize("model_name", openai_reasoning_summary_models())
async def test_openai_reasoning_summaries_paid(
    tmp_path, model_name: str, streamed: bool
):
    skip_if_missing_provider_keys(ModelProviderName.openai)
    task = build_thinking_level_test_task(tmp_path)
    # Four of these models default to "none", which returns no summary, so every
    # case runs at medium.
    run_config = KilnAgentRunConfigProperties(
        model_name=model_name,
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_prompt_builder",
        structured_output_mode="default",
        thinking_level="medium",
    )
    adapter = LiteLlmAdapter(
        config=dataclasses.replace(
            litellm_core_provider_config(run_config), openai_reasoning_summaries=True
        ),
        kiln_task=task,
    )

    if streamed:
        stream = adapter.invoke_openai_stream(LOGIC_PUZZLE_PROMPT)
        async for _ in stream:
            pass
        run = stream.task_run
    else:
        run = await adapter.invoke(LOGIC_PUZZLE_PROMPT)

    assert run.intermediate_outputs is not None
    reasoning = run.intermediate_outputs.get("reasoning")
    assert isinstance(reasoning, str) and reasoning.strip(), (
        f"Expected a reasoning summary from {model_name} (streamed={streamed})"
    )


def openai_reasoning_summary_models_with_none() -> list[str]:
    return [
        model.name
        for model in built_in_models
        for provider in model.providers
        if provider.name == ModelProviderName.openai
        and provider.openai_reasoning_summary is not None
        and provider.available_thinking_levels is not None
        and "none" in provider.available_thinking_levels.values()
    ]


# With summaries on, a "none" run still goes to /v1/responses, and several of these
# providers default to "none". OpenAI must accept it and return no reasoning.
@pytest.mark.paid
@pytest.mark.parametrize("model_name", openai_reasoning_summary_models_with_none())
async def test_openai_reasoning_summaries_at_none_paid(tmp_path, model_name: str):
    skip_if_missing_provider_keys(ModelProviderName.openai)
    task = build_thinking_level_test_task(tmp_path)
    run_config = KilnAgentRunConfigProperties(
        model_name=model_name,
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_prompt_builder",
        structured_output_mode="default",
        thinking_level="none",
    )
    adapter = LiteLlmAdapter(
        config=dataclasses.replace(
            litellm_core_provider_config(run_config), openai_reasoning_summaries=True
        ),
        kiln_task=task,
    )

    run = await adapter.invoke(LOGIC_PUZZLE_PROMPT)

    assert run.output.output
    assert reasoning_content_from_run(run) is None


# Curated prerelease smoke test: same behavior as test_thinking_level_reasoning_content
# above, restricted to a small whitelist so --runprerelease stays fast.
@pytest.mark.paid
@pytest.mark.prerelease
@pytest.mark.parametrize(
    ("provider_name", "model_name", "thinking_level"),
    PRERELEASE_THINKING_MODELS,
)
async def test_thinking_level_reasoning_content_prerelease_smoke(
    tmp_path, provider_name: str, model_name: str, thinking_level: str
):
    skip_if_missing_provider_keys(provider_name)
    # Anthropic requires temperature 1 with thinking on, and GPT-6 rejects any other
    # value. 1 is Kiln's default, so every model in the catalog accepts it.
    temperature = 1

    task = build_thinking_level_test_task(tmp_path)
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            thinking_level=thinking_level,
            temperature=temperature,
            top_p=1,
        ),
    )
    run = await adapter.invoke(LOGIC_PUZZLE_PROMPT)
    reasoning_content = reasoning_content_from_run(run)
    if thinking_level == "none":
        assert reasoning_content is None, (
            f"Expected no reasoning content for thinking_level='none', "
            f"but got {len(reasoning_content) if reasoning_content else 0} chars "
            f"(provider={provider_name}, model={model_name})"
        )
    else:
        assert reasoning_content is not None, (
            f"Expected reasoning content for thinking_level='{thinking_level}', "
            f"but got None "
            f"(provider={provider_name}, model={model_name})"
        )
