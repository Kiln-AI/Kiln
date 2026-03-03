from pathlib import Path

import pytest

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName, built_in_models
from kiln_ai.adapters.provider_tools import provider_warnings
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.utils.config import Config


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
            reasoning = message.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning.strip()

    return None


def skip_if_missing_provider_keys(provider_name) -> None:
    warning = provider_warnings.get(provider_name)
    if warning is None:
        return
    missing = [
        key
        for key in warning.required_config_keys
        if not Config.shared().get_value(key)
    ]
    if missing:
        missing_list = ", ".join(missing)
        pytest.skip(
            f"Missing config keys for {provider_name}: {missing_list}. "
            "Set env vars or .env before running paid tests."
        )


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
            ModelProviderName.openai,
            ModelProviderName.openrouter,
            ModelProviderName.gemini_api,
            ModelProviderName.vertex,
        ]
    ),
)
async def test_thinking_level_reasoning_content(
    tmp_path, provider_name: str, model_name: str, thinking_level: str
):
    skip_if_missing_provider_keys(provider_name)
    task = build_thinking_level_test_task(tmp_path)
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            thinking_level=thinking_level,
            temperature=0,
            top_p=1,
        ),
    )
    run = await adapter.invoke(
        "Four people-A, B, C, and D-each have a different favorite color (red, blue, green, yellow) and a different pet (cat, dog, fish, bird). Use the clues to determine each person's color and pet.\n\n1) A does not like red or blue.\n2) The bird's owner likes yellow.\n3) B likes green.\n4) The dog is owned by the person who likes blue.\n5) C does not own the fish.\n6) D likes red.\n\nQuestion: Who owns the fish, and what color do they like? Answer with just: \"<person>, <color>\"."
    )
    reasoning_content = reasoning_content_from_run(run)

    if thinking_level == "none":
        assert reasoning_content is None, (
            "expected no reasoning_content when thinking_level is none"
        )
    else:
        assert reasoning_content is not None, "missing reasoning_content"
