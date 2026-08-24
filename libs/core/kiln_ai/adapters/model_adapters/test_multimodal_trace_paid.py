"""End-to-end paid tests for multimodal (list-valued) message content in a trace.

A message's `content` is normally a string. For a multimodal message it is a list of
parts instead - text plus an image, audio or a file. That list is the only copy of the
image: nothing else in a TaskRun carries it, so if it is dropped on the way to disk it
is gone for good.

It used to be dropped. Every role declared `content` as `Iterable[T]`, which pydantic
validates into a single-use iterator; serializing read it, the read emptied it, and
`save_to_file` wrote `content: []` with no error and no warning. The unit tests in
`libs/core/kiln_ai/utils/test_open_ai_types.py` pin the model layer. These run the whole
path against a real provider: a real image goes to a real multimodal model, the answer
proves the model received the image, and the image part is read back off disk afterwards.
"""

from pathlib import Path

import pytest

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.extractors.litellm_extractor import encode_file_litellm_format
from kiln_ai.adapters.pytest_prerelease_whitelist import (
    PRERELEASE_MULTIMODAL_TRACE_MODELS,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.pytest_mock_files import MockFileFactoryMimeType
from kiln_ai.utils.open_ai_types import (
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParamWrapper,
)

# The PNG the mock file factory hands back is the Kodak "kodim23" parrots photo. Any
# model that actually looked at it says one of these; a model that received an empty
# content list cannot.
IMAGE_ANSWER_TERMS = ["parrot", "bird", "macaw"]


def build_multimodal_task(tmp_path: Path) -> datamodel.Task:
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()

    task = datamodel.Task(
        parent=project,
        name="describe the image",
        instruction=(
            "You describe images. Answer the user's question about the image they "
            "sent, in one short sentence."
        ),
    )
    task.save_to_file()
    return task


def build_image_message(
    image_path: Path, provider: ModelProviderName
) -> ChatCompletionUserMessageParamWrapper:
    """A user message whose content is a list of parts: text, then a real PNG."""
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "Here is an image."},
            encode_file_litellm_format(
                image_path, MockFileFactoryMimeType.PNG.value, provider
            ),
        ],
    }


def image_part_of(message: ChatCompletionMessageParam) -> dict:
    content = message["content"]
    assert isinstance(content, list), (
        f"content is a {type(content).__name__}, not a list of parts - the multimodal "
        "message lost its parts"
    )
    assert len(content) == 2, f"expected 2 content parts, got {len(content)}"
    return content[1]


def run_config(model_name: str, provider: str) -> KilnAgentRunConfigProperties:
    return KilnAgentRunConfigProperties(
        model_name=model_name,
        model_provider_name=ModelProviderName(provider),
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
    )


@pytest.mark.paid
@pytest.mark.prerelease
@pytest.mark.parametrize("model_name, provider", PRERELEASE_MULTIMODAL_TRACE_MODELS)
async def test_multimodal_trace_survives_save_to_file(
    tmp_path, mock_file_factory, model_name, provider
):
    """The full flow, end to end: a real image reaches a real model, and the image
    part is still on disk when the run is read back."""
    task = build_multimodal_task(tmp_path)
    image_path = mock_file_factory(MockFileFactoryMimeType.PNG)
    image_message = build_image_message(image_path, ModelProviderName(provider))

    adapter = adapter_for_task(task, run_config(model_name, provider))
    run = await adapter.invoke(
        input="What animal is in the image?",
        prior_trace=[image_message],
    )

    # The model answered from the image, so the image really was sent.
    assert any(term in run.output.output.lower() for term in IMAGE_ANSWER_TERMS), (
        f"model did not describe the image. Response: {run.output.output}"
    )

    # invoke() saved the run (autosave_runs defaults on, and the task has a path).
    assert run.path is not None, "run was not saved - nothing to read back"
    reloaded = TaskRun.load_from_file(run.path)

    assert reloaded.trace is not None
    assert image_part_of(reloaded.trace[0]) == image_message["content"][1]
    assert image_part_of(reloaded.trace[0])["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


@pytest.mark.paid
async def test_multimodal_trace_survives_a_second_turn_and_a_second_save(
    tmp_path, mock_file_factory
):
    """The original bug lost some roles' content only on the *second* write, so one
    save proving correct was never enough.

    A second turn is how that happens in practice: the stored trace is loaded, seeded
    back in as `prior_trace`, extended by a new exchange, and saved again. The image
    part has to survive both writes, and the model has to still see it on turn two.
    """
    model_name, provider = PRERELEASE_MULTIMODAL_TRACE_MODELS[0]
    task = build_multimodal_task(tmp_path)
    image_path = mock_file_factory(MockFileFactoryMimeType.PNG)
    image_message = build_image_message(image_path, ModelProviderName(provider))

    adapter = adapter_for_task(task, run_config(model_name, provider))
    first_run = await adapter.invoke(
        input="What animal is in the image?",
        prior_trace=[image_message],
    )
    assert first_run.path is not None
    first_trace = TaskRun.load_from_file(first_run.path).trace
    assert first_trace is not None

    second_run = await adapter.invoke(
        input="What colors is it? Name the animal again in your answer.",
        prior_trace=list(first_trace),
    )

    # Turn two still had the image: the model names the animal without being told it.
    assert any(
        term in second_run.output.output.lower() for term in IMAGE_ANSWER_TERMS
    ), f"model lost the image on the second turn. Response: {second_run.output.output}"

    assert second_run.path is not None
    reloaded = TaskRun.load_from_file(second_run.path)
    assert reloaded.trace is not None
    assert image_part_of(reloaded.trace[0]) == image_message["content"][1]

    # And saving the loaded run again does not empty it either.
    resaved = reloaded.mutable_copy()
    resaved.save_to_file()
    assert resaved.path is not None
    assert (
        image_part_of(TaskRun.load_from_file(resaved.path).trace[0])
        == (image_message["content"][1])
    )
