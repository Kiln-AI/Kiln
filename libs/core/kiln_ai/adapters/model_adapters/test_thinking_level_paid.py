from pathlib import Path

import pytest

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import built_in_models
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


def get_thinking_levels_for_provider(provider) -> list[str]:
    """Get all thinking levels for a provider."""
    if not provider.available_thinking_levels:
        return []
    return list(provider.available_thinking_levels.values())


def get_thinking_model_provider_levels() -> list[tuple[str, str, str]]:
    """Get the thinking model, provider and level for all models that support thinking."""
    params: list[tuple[str, str, str]] = []
    for model in built_in_models:
        for provider in model.providers:
            if not provider.model_id:
                continue
            if not provider.available_thinking_levels:
                continue

            levels = get_thinking_levels_for_provider(provider)
            for level in levels:
                params.append((model.name, provider.name, level))
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


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_name, provider_name, thinking_level", get_thinking_model_provider_levels()
)
async def test_thinking_level_reasoning_content(
    tmp_path, model_name: str, provider_name: str, thinking_level: str
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
        "A is older than B. B is older than C. C is older than D. Who is the second oldest? Answer with just the name."
    )
    reasoning_content = reasoning_content_from_run(run)

    if thinking_level == "none":
        assert reasoning_content is None
    else:
        assert reasoning_content is not None
