import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Tuple
from unittest.mock import patch

import litellm
import pytest
from litellm.types.utils import ChatCompletionDeltaToolCall

from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, PromptGenerators, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId

logger = logging.getLogger(__name__)


class ChunkRendererAbstract(ABC):
    @abstractmethod
    async def render_chunk(self, chunk: litellm.ModelResponseStream):
        pass

    @abstractmethod
    def get_stream_text(self) -> str:
        pass


class ChunkRenderer(ChunkRendererAbstract):
    def __init__(self):
        self.chunk_texts: list[str] = []
        self.current_block_type: str | None = None

    def print_and_append(self, text: str):
        # replace with print if your logger is not outputting info logs
        logger.info(text)
        self.chunk_texts.append(text)

    def enter_block(self, block_type: str):
        if self.current_block_type != block_type:
            if self.current_block_type is not None:
                self.print_and_append(f"</{self.current_block_type}>\n")

            self.print_and_append(f"\n<{block_type}>\n")
            self.current_block_type = block_type

    def render_reasoning(self, reasoning_content: str):
        self.enter_block("reasoning")
        self.print_and_append(reasoning_content)

    def render_content(self, content: str):
        self.enter_block("content")
        self.print_and_append(content)

    def render_tool_call(self, tool_calls: list[ChatCompletionDeltaToolCall | Any]):
        self.enter_block("tool_call")
        for tool_call in tool_calls:
            # first it says the tool name, then the arguments
            if tool_call.function.name is not None:
                self.print_and_append(f'Calling tool: "{tool_call.function.name}" ')
                self.print_and_append("with args: ")
            elif tool_call.function.arguments is not None:
                args = tool_call.function.arguments
                self.print_and_append(args)

    def render_stop(self, stop_reason: str):
        self.print_and_append("\n")

    def render_unknown(self, chunk: litellm.ModelResponseStream):
        self.enter_block("unknown")
        self.print_and_append(f"Unknown chunk: {chunk}")

    async def render_chunk(self, chunk: litellm.ModelResponseStream):
        if chunk.choices[0].finish_reason is not None:
            self.render_stop(chunk.choices[0].finish_reason)
            return
        elif chunk.choices[0].delta is not None:
            # inconsistent behavior between providers, some have multiple fields at once, some don't
            if chunk.choices[0].delta.tool_calls is not None:
                self.render_tool_call(chunk.choices[0].delta.tool_calls)
            elif getattr(chunk.choices[0].delta, "reasoning_content", None) is not None:
                text = getattr(chunk.choices[0].delta, "reasoning_content", None)
                if text is not None:
                    self.render_reasoning(text)
            elif chunk.choices[0].delta.content is not None:
                self.render_content(chunk.choices[0].delta.content)
        else:
            self.render_unknown(chunk)

    def get_stream_text(self) -> str:
        return "".join(self.chunk_texts)


class ChunkRawRenderer(ChunkRendererAbstract):
    def __init__(self):
        self.chunks: list[litellm.ModelResponseStream] = []
        self.current_block_type: str | None = None

    async def render_chunk(self, chunk: litellm.ModelResponseStream):
        logger.info(str(chunk))
        self.chunks.append(chunk)

    def get_stream_text(self) -> str:
        return "\n".join([str(chunk) for chunk in self.chunks])


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
        ("claude_sonnet_4_5_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_5_thinking", ModelProviderName.anthropic),
        ("claude_sonnet_4_6_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_6_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_5_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_5_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_6_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_6_thinking", ModelProviderName.anthropic),
        ("claude_4_5_haiku_thinking", ModelProviderName.openrouter),
        ("claude_4_5_haiku_thinking", ModelProviderName.anthropic),
        ("minimax_m2_5", ModelProviderName.openrouter),
    ],
)
async def test_acompletion_streaming_response(
    model_id: str,
    provider_name: ModelProviderName,
    adapter_factory: Callable[[str, ModelProviderName], LiteLlmAdapter],
):
    """Check the accumulated response has all the expected parts"""
    adapter = adapter_factory(model_id, provider_name)

    renderer = ChunkRenderer()

    # we proxy all the calls to the original function so we can spy on the return values
    captured_responses: list[Tuple[litellm.ModelResponse, litellm.Choices]] = []
    origin_func = adapter.acompletion_checking_response

    async def spy(
        *args: Any, **kwargs: Any
    ) -> Tuple[litellm.ModelResponse, litellm.Choices]:
        nonlocal captured_responses

        result = await origin_func(*args, **kwargs)
        captured_responses.append(result)
        return result

    with patch.object(adapter, "acompletion_checking_response", side_effect=spy):
        task_run = await adapter.invoke(
            input="123 + 321 = ?",
            on_chunk=renderer.render_chunk,
        )

    # there is one call per thing going on (tool call, content, etc.)
    # with our toy task, we expect ~2 or 3 calls (reasoning + tool call -> content)
    if len(captured_responses) == 0:
        raise RuntimeError(
            "captured_responses is empty after invocation - test probably broken due to wrong spy"
        )

    # check we are getting the trace successfully
    assert task_run.trace is not None, "Task run trace is None"
    assert len(task_run.trace) > 0, "Task run trace is empty"

    assistant_messages: list[litellm.Message] = []
    for model_response, _ in captured_responses:
        for choice in model_response.choices:
            if isinstance(choice, litellm.Choices):
                assistant_messages.append(choice.message)
    assert len(assistant_messages) > 0, "No assistant messages found in the trace"

    # we do not know which message the reasoning / content / tool call is in, but we know each one
    # should appear in at least one message so we accumulate them here
    reasoning_contents: list[str] = []
    contents: list[str] = []
    tool_calls: list[ChatCompletionDeltaToolCall | Any] = []
    for assistant_message in assistant_messages:
        reasoning_content = getattr(assistant_message, "reasoning_content", None)
        if reasoning_content:
            reasoning_contents.append(reasoning_content)

        content = getattr(assistant_message, "content", None)
        if content:
            contents.append(str(content))

        _tool_calls = getattr(assistant_message, "tool_calls", None)
        if _tool_calls:
            tool_calls.extend(_tool_calls)

    # check we got all the expected parts somewhere
    assert len(reasoning_contents) > 0, "No reasoning contents found in the trace"
    assert len(contents) > 0, "No contents found in the trace"
    assert len(tool_calls) > 0, "No tool calls found in the trace"
    assert len(tool_calls) == 1, "Expected exactly one tool call (to do the math)"

    # check we got some non-empty reasoning - we should have gotten some reasoning at least somewhere
    # usually the toolcall
    assert not all(
        reasoning_content.strip() == "" for reasoning_content in reasoning_contents
    ), "All reasoning contents are empty"

    # check we got some non-empty content (we get empty strings when there is no content)
    assert not all(content.strip() == "" for content in contents), (
        "All contents are empty"
    )

    for tool_call in tool_calls:
        assert tool_call.function.name is not None, "Tool call name is None"
        assert tool_call.function.arguments is not None, "Tool call arguments are None"
        assert json.loads(tool_call.function.arguments) is not None, (
            "Tool call arguments are not JSON"
        )
        tool_call_args = json.loads(tool_call.function.arguments)
        assert tool_call_args == {
            "a": 123,
            "b": 321,
        } or tool_call_args == {
            "a": 321,
            "b": 123,
        }, f"Tool call arguments are not the expected values: {tool_call_args}"


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name",
    [
        ("claude_sonnet_4_5_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_5_thinking", ModelProviderName.anthropic),
        ("claude_sonnet_4_6_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_6_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_5_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_5_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_6_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_6_thinking", ModelProviderName.anthropic),
        ("claude_4_5_haiku_thinking", ModelProviderName.openrouter),
        ("claude_4_5_haiku_thinking", ModelProviderName.anthropic),
        ("minimax_m2_5", ModelProviderName.openrouter),
    ],
)
async def test_acompletion_streaming_chunks(
    model_id: str,
    provider_name: ModelProviderName,
    adapter_factory: Callable[[str, ModelProviderName], LiteLlmAdapter],
):
    """Collect all chunks from all completion calls, then one pass to check we got reasoning, content, and tool calls."""

    adapter = adapter_factory(model_id, provider_name)

    chunks: list[litellm.ModelResponseStream] = []

    renderer = ChunkRenderer()

    async def collect_chunks(chunk: litellm.ModelResponseStream) -> None:
        chunks.append(chunk)
        await renderer.render_chunk(chunk)

    await adapter.invoke(input="123 + 321 = ?", on_chunk=collect_chunks)

    assert len(chunks) > 0, "No chunks collected"
    reasoning_contents: list[str] = []
    contents: list[str] = []
    tool_calls: list[ChatCompletionDeltaToolCall | Any] = []

    for chunk in chunks:
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

    assert len(reasoning_contents) > 0, "No reasoning content in chunks"
    assert len(contents) > 0, "No content in chunks"
    assert len(tool_calls) > 0, "No tool calls in chunks"
    assert not all(r.strip() == "" for r in reasoning_contents), (
        "All reasoning content in chunks is empty"
    )
    assert not all(c.strip() == "" for c in contents), "All content in chunks is empty"

    tool_call_function_names = [
        tool_call.function.name
        for tool_call in tool_calls
        if tool_call.function.name is not None
    ]
    assert len(tool_call_function_names) == 1, (
        "Expected exactly one tool call function name"
    )
    assert tool_call_function_names[0] == "add", "Tool call function name is not 'add'"

    tool_call_args_chunks = "".join(
        [
            tool_call.function.arguments
            for tool_call in tool_calls
            if tool_call.function.arguments is not None
        ]
    )

    tool_call_args = json.loads(tool_call_args_chunks)
    assert tool_call_args == {"a": 123, "b": 321} or tool_call_args == {
        "a": 321,
        "b": 123,
    }, f"Tool call arguments not as expected: {tool_call_args}"


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name",
    [
        ("claude_sonnet_4_5_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_5_thinking", ModelProviderName.anthropic),
        ("claude_sonnet_4_6_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_6_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_5_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_5_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_6_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_6_thinking", ModelProviderName.anthropic),
        ("claude_4_5_haiku_thinking", ModelProviderName.openrouter),
        ("claude_4_5_haiku_thinking", ModelProviderName.anthropic),
        ("minimax_m2_5", ModelProviderName.openrouter),
    ],
)
async def test_acompletion_streaming_rendering(
    model_id: str,
    provider_name: ModelProviderName,
    adapter_factory: Callable[[str, ModelProviderName], LiteLlmAdapter],
):
    """Test that the streaming response with a renderer to see how it looks"""
    adapter = adapter_factory(model_id, provider_name)
    renderer = ChunkRenderer()
    await adapter.invoke(input="123 + 321 = ?", on_chunk=renderer.render_chunk)
    assert renderer.get_stream_text() is not None


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name",
    [
        ("claude_sonnet_4_5_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_5_thinking", ModelProviderName.anthropic),
        ("claude_sonnet_4_6_thinking", ModelProviderName.openrouter),
        ("claude_sonnet_4_6_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_5_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_5_thinking", ModelProviderName.anthropic),
        ("claude_opus_4_6_thinking", ModelProviderName.openrouter),
        ("claude_opus_4_6_thinking", ModelProviderName.anthropic),
        ("claude_4_5_haiku_thinking", ModelProviderName.openrouter),
        ("claude_4_5_haiku_thinking", ModelProviderName.anthropic),
        ("minimax_m2_5", ModelProviderName.openrouter),
    ],
)
async def test_acompletion_streaming_rendering_raw_chunks(
    model_id: str,
    provider_name: ModelProviderName,
    adapter_factory: Callable[[str, ModelProviderName], LiteLlmAdapter],
):
    """Test that the streaming response with a renderer to see how it looks, but with raw chunks"""
    adapter = adapter_factory(model_id, provider_name)
    renderer = ChunkRawRenderer()
    await adapter.invoke(input="123 + 321 = ?", on_chunk=renderer.render_chunk)
    assert renderer.get_stream_text() is not None
