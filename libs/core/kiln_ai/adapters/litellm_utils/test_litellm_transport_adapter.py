import json
from pathlib import Path
from typing import Callable

import pytest
from litellm.types.utils import ChatCompletionDeltaToolCall, ModelResponseStream

from kiln_ai.adapters.litellm_utils.litellm_transport_adapter import (
    AISDKStreamTransport,
)
from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, PromptGenerators, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId


@pytest.fixture
def task(tmp_path):
    project_path: Path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    task = Task(
        name="Streaming Test Task",
        instruction="Think about it hard! Solve the math problem provided by the user, in a step by step manner. Use the tools provided to solve the math problem. Then use the result in a short sentence about a cat going to the mall. Remember to use the tools for math even if the operation looks easy.",
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def adapter_factory(task: Task) -> Callable[[str, ModelProviderName], LiteLlmAdapter]:
    def create_adapter(
        model_id: str, provider_name: ModelProviderName
    ) -> LiteLlmAdapter:
        adapter = LiteLlmAdapter(
            kiln_task=task,
            config=LiteLlmConfig(
                run_config_properties=KilnAgentRunConfigProperties(
                    model_name=model_id,
                    model_provider_name=provider_name,
                    prompt_id=PromptGenerators.SIMPLE,
                    structured_output_mode=StructuredOutputMode.unknown,
                    tools_config=ToolsRunConfig(
                        tools=[
                            KilnBuiltInToolId.ADD_NUMBERS,
                            KilnBuiltInToolId.SUBTRACT_NUMBERS,
                            KilnBuiltInToolId.MULTIPLY_NUMBERS,
                            KilnBuiltInToolId.DIVIDE_NUMBERS,
                        ],
                    ),
                )
            ),
        )
        return adapter

    return create_adapter


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name",
    [
        ("claude_sonnet_4_5", ModelProviderName.openrouter),
        ("claude_sonnet_4_5", ModelProviderName.anthropic),
    ],
)
async def test_openai_stream_transport_output(
    model_id: str,
    provider_name: ModelProviderName,
    adapter_factory: Callable[[str, ModelProviderName], LiteLlmAdapter],
):
    chunks: list[ModelResponseStream] = []

    async def collect_chunk(chunk: ModelResponseStream) -> None:
        chunks.append(chunk)

    adapter = adapter_factory(model_id, provider_name)
    await adapter.invoke(input="123 + 321 = ?", stream_transport=collect_chunk)

    assert len(chunks) > 0
    reasoning_contents: list[str] = []
    contents: list[str] = []
    tool_calls: list[ChatCompletionDeltaToolCall] = []

    for chunk in chunks:
        if not chunk.choices:
            continue
        if chunk.choices[0].finish_reason is not None:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        if delta.tool_calls is not None:
            tool_calls.extend(delta.tool_calls)
        elif getattr(delta, "reasoning_content", None) is not None:
            text = getattr(delta, "reasoning_content", None)
            if text is not None:
                reasoning_contents.append(text)
        elif delta.content is not None:
            contents.append(delta.content)

    assert len(reasoning_contents) > 0
    assert len(contents) > 0
    assert len(tool_calls) > 0
    assert not all(r.strip() == "" for r in reasoning_contents)
    assert not all(c.strip() == "" for c in contents)

    tool_call_function_names = [
        tc.function.name for tc in tool_calls if tc.function.name is not None
    ]
    assert len(tool_call_function_names) >= 1
    assert tool_call_function_names[0] == "add"

    tool_call_args_chunks = "".join(
        [tc.function.arguments for tc in tool_calls if tc.function.arguments]
    )
    tool_call_args = json.loads(tool_call_args_chunks)
    assert tool_call_args in ({"a": 123, "b": 321}, {"a": 321, "b": 123})


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name",
    [
        ("claude_sonnet_4_5", ModelProviderName.openrouter),
        ("claude_sonnet_4_5", ModelProviderName.anthropic),
    ],
)
async def test_aisdk_stream_transport_output(
    model_id: str,
    provider_name: ModelProviderName,
    adapter_factory: Callable[[str, ModelProviderName], LiteLlmAdapter],
):
    parts: list[dict | str] = []

    async def append_part(part: dict | str) -> None:
        parts.append(part)

    transport = AISDKStreamTransport(on_part=append_part)
    adapter = adapter_factory(model_id, provider_name)
    await adapter.invoke(input="123 + 321 = ?", stream_transport=transport)

    assert len(parts) > 0

    part_types = [p.get("type") for p in parts if isinstance(p, dict)]
    assert "start" in part_types
    assert "start-step" in part_types
    assert "finish-step" in part_types
    assert "finish" in part_types

    has_text_or_reasoning = (
        "text-delta" in part_types or "reasoning-delta" in part_types
    )
    assert has_text_or_reasoning

    has_tool_parts = (
        "tool-input-start" in part_types
        or "tool-input-delta" in part_types
        or "tool-input-available" in part_types
    )
    assert has_tool_parts

    assert "[DONE]" in parts
