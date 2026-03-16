import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import litellm
import pytest
from litellm.types.utils import ChatCompletionDeltaToolCall

from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.adapters.model_adapters.stream_events import (
    AiSdkEventType,
    AiSdkStreamEvent,
)
from kiln_ai.datamodel import Project, PromptGenerators, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId

logger = logging.getLogger(__name__)

STREAMING_MODELS = [
    ("claude_sonnet_4_5", ModelProviderName.openrouter, "medium"),
    ("claude_sonnet_4_5", ModelProviderName.anthropic, "medium"),
    ("claude_sonnet_4_6", ModelProviderName.openrouter, "medium"),
    ("claude_sonnet_4_6", ModelProviderName.anthropic, "medium"),
    ("claude_opus_4_5", ModelProviderName.openrouter, "medium"),
    ("claude_opus_4_5", ModelProviderName.anthropic, "medium"),
    ("claude_opus_4_6", ModelProviderName.openrouter, "medium"),
    ("claude_opus_4_6", ModelProviderName.anthropic, "medium"),
    ("minimax_m2_5", ModelProviderName.openrouter, "medium"),
    ("claude_4_5_haiku", ModelProviderName.openrouter, "medium"),
    ("claude_4_5_haiku", ModelProviderName.anthropic, "medium"),
]

PAID_TEST_OUTPUT_DIR = Path(__file__).resolve().parents[5] / "test_output"


def _serialize_for_dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        if not obj:
            return []
        first = obj[0]
        if hasattr(first, "type") and hasattr(first, "payload"):
            return [{"type": e.type.value, "payload": e.payload} for e in obj]
        if hasattr(first, "model_dump"):
            return [item.model_dump(mode="json") for item in obj]
        return [_serialize_for_dump(x) for x in obj]
    return obj


def _dump_paid_test_output(request: pytest.FixtureRequest, **payloads: Any) -> Path:
    test_name = re.sub(r"[^\w\-]", "_", request.node.name)
    param_id = "default"
    if hasattr(request.node, "callspec") and request.node.callspec is not None:
        id_attr = getattr(request.node.callspec, "id", None)
        if id_attr is not None:
            param_id = re.sub(r"[^\w\-]", "_", str(id_attr))
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = PAID_TEST_OUTPUT_DIR / test_name / param_id / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, data in payloads.items():
        if data is None:
            continue
        if not filename.endswith(".json"):
            filename = f"{filename}.json"
        serialized = _serialize_for_dump(data)
        (out_dir / filename).write_text(
            json.dumps(serialized, indent=2, default=str), encoding="utf-8"
        )
    return out_dir


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
def adapter_factory(
    task: Task,
) -> Callable[[str, ModelProviderName, str | None], LiteLlmAdapter]:
    def create_adapter(
        model_id: str, provider_name: ModelProviderName, thinking_level: str | None
    ) -> LiteLlmAdapter:
        return LiteLlmAdapter(
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
                    thinking_level=thinking_level,
                )
            ),
        )

    return create_adapter


@pytest.mark.paid
@pytest.mark.parametrize("model_id,provider_name,thinking_level", STREAMING_MODELS)
async def test_invoke_openai_stream_chunks(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    adapter_factory: Callable[[str, ModelProviderName, str | None], LiteLlmAdapter],
):
    """Collect all OpenAI-protocol chunks via invoke_openai_stream and verify we got reasoning, content, and tool call data."""
    adapter = adapter_factory(model_id, provider_name, thinking_level)

    chunks: list[litellm.ModelResponseStream] = []
    async for chunk in adapter.invoke_openai_stream(input="123 + 321 = ?"):
        chunks.append(chunk)

    _dump_paid_test_output(request, chunks=chunks)
    assert len(chunks) > 0, "No chunks collected"

    reasoning_contents: list[str] = []
    contents: list[str] = []
    tool_calls: list[ChatCompletionDeltaToolCall | Any] = []

    for chunk in chunks:
        if len(chunk.choices) == 0:
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

    assert len(reasoning_contents) > 0, "No reasoning content in chunks"
    assert len(contents) > 0, "No content in chunks"
    assert len(tool_calls) > 0, "No tool calls in chunks"
    assert not all(r.strip() == "" for r in reasoning_contents), (
        "All reasoning content in chunks is empty"
    )
    assert not all(c.strip() == "" for c in contents), "All content in chunks is empty"

    tool_call_function_names = [
        tc.function.name for tc in tool_calls if tc.function.name is not None
    ]
    assert len(tool_call_function_names) == 1, (
        "Expected exactly one tool call function name"
    )
    assert tool_call_function_names[0] == "add", "Tool call function name is not 'add'"

    tool_call_args_chunks = "".join(
        tc.function.arguments for tc in tool_calls if tc.function.arguments is not None
    )
    tool_call_args = json.loads(tool_call_args_chunks)
    assert tool_call_args == {"a": 123, "b": 321} or tool_call_args == {
        "a": 321,
        "b": 123,
    }, f"Tool call arguments not as expected: {tool_call_args}"


@pytest.mark.paid
@pytest.mark.parametrize("model_id,provider_name,thinking_level", STREAMING_MODELS)
async def test_invoke_ai_sdk_stream(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    adapter_factory: Callable[[str, ModelProviderName, str | None], LiteLlmAdapter],
):
    """Collect AI SDK events and verify the full protocol lifecycle including tool events."""
    adapter = adapter_factory(model_id, provider_name, thinking_level)

    events: list[AiSdkStreamEvent] = []
    async for event in adapter.invoke_ai_sdk_stream(input="123 + 321 = ?"):
        events.append(event)
        logger.info(f"AI SDK event: {event.type.value} {event.payload}")

    _dump_paid_test_output(request, events=events)
    assert len(events) > 0, "No events collected"

    event_types = [e.type for e in events]

    assert event_types[0] == AiSdkEventType.START, "First event should be START"
    assert event_types[1] == AiSdkEventType.START_STEP, (
        "Second event should be START_STEP"
    )

    assert AiSdkEventType.FINISH_STEP in event_types, "Should have FINISH_STEP"
    assert AiSdkEventType.FINISH in event_types, "Should have FINISH"
    finish_step_idx = event_types.index(AiSdkEventType.FINISH_STEP)
    finish_idx = event_types.index(AiSdkEventType.FINISH)
    assert finish_step_idx < finish_idx, (
        f"FINISH_STEP (idx {finish_step_idx}) must come before FINISH (idx {finish_idx})"
    )

    assert AiSdkEventType.REASONING_START in event_types, "Should have REASONING_START"
    assert AiSdkEventType.REASONING_DELTA in event_types, "Should have REASONING_DELTA"

    assert AiSdkEventType.TEXT_START in event_types, "Should have TEXT_START"
    assert AiSdkEventType.TEXT_DELTA in event_types, "Should have TEXT_DELTA"
    assert AiSdkEventType.TEXT_END in event_types, "Should have TEXT_END"

    assert AiSdkEventType.TOOL_INPUT_START in event_types, (
        "Should have TOOL_INPUT_START"
    )
    assert AiSdkEventType.TOOL_INPUT_AVAILABLE in event_types, (
        "Should have TOOL_INPUT_AVAILABLE"
    )
    assert AiSdkEventType.TOOL_OUTPUT_AVAILABLE in event_types, (
        "Should have TOOL_OUTPUT_AVAILABLE"
    )

    text_deltas = [
        e.payload.get("delta", "")
        for e in events
        if e.type == AiSdkEventType.TEXT_DELTA
    ]
    full_text = "".join(text_deltas)
    assert len(full_text) > 0, "Text content is empty"

    tool_input_available = [
        e for e in events if e.type == AiSdkEventType.TOOL_INPUT_AVAILABLE
    ]
    assert len(tool_input_available) >= 1, (
        "Should have at least one tool-input-available"
    )
    tool_input = tool_input_available[0].payload.get("input", {})
    assert "a" in tool_input and "b" in tool_input, (
        f"Tool input should have a and b keys: {tool_input}"
    )

    tool_output_available = [
        e for e in events if e.type == AiSdkEventType.TOOL_OUTPUT_AVAILABLE
    ]
    assert len(tool_output_available) >= 1, (
        "Should have at least one tool-output-available"
    )
    assert tool_output_available[0].payload.get("output") is not None, (
        "Tool output should not be None"
    )


@pytest.mark.paid
@pytest.mark.parametrize("model_id,provider_name,thinking_level", STREAMING_MODELS)
async def test_ai_sdk_stream_text_ends_before_tool_calls(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    adapter_factory: Callable[[str, ModelProviderName, str | None], LiteLlmAdapter],
):
    """Verify text blocks are properly closed before tool-input-start and reopened with a new ID after tool execution."""
    adapter = adapter_factory(model_id, provider_name, thinking_level)

    events: list[AiSdkStreamEvent] = []
    async for event in adapter.invoke_ai_sdk_stream(
        input="First tell me you're about to calculate, then compute 11 + 50 and 50 * 85, then add the results. Use the tools for all math."
    ):
        events.append(event)

    _dump_paid_test_output(request, events=events)

    event_types = [e.type for e in events]
    assert AiSdkEventType.TEXT_START in event_types, "Should have TEXT_START"
    assert AiSdkEventType.TOOL_INPUT_START in event_types, (
        "Should have TOOL_INPUT_START"
    )

    text_ids_seen: list[str] = []
    text_open = False
    for event in events:
        if event.type == AiSdkEventType.TEXT_START:
            assert not text_open, (
                "text-start emitted while a text block was already open"
            )
            text_open = True
            text_ids_seen.append(event.payload["id"])

        elif event.type == AiSdkEventType.TEXT_END:
            assert text_open, "text-end emitted without a preceding text-start"
            text_open = False

        elif event.type == AiSdkEventType.TEXT_DELTA:
            assert text_open, (
                f"text-delta emitted outside an open text block: {event.payload}"
            )

        elif event.type == AiSdkEventType.TOOL_INPUT_START:
            assert not text_open, (
                "tool-input-start emitted while text block was still open "
                "(missing text-end before tool calls)"
            )

    assert len(text_ids_seen) >= 2, (
        f"Expected at least 2 distinct text blocks (before and after tool calls), "
        f"got {len(text_ids_seen)}: {text_ids_seen}"
    )
    assert len(set(text_ids_seen)) == len(text_ids_seen), (
        f"Each text block should have a unique ID, got duplicates: {text_ids_seen}"
    )


@pytest.mark.paid
@pytest.mark.parametrize("model_id,provider_name,thinking_level", STREAMING_MODELS)
async def test_invoke_openai_stream_non_streaming_still_works(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    adapter_factory: Callable[[str, ModelProviderName, str | None], LiteLlmAdapter],
):
    """Verify the non-streaming invoke() still works after the refactor."""
    adapter = adapter_factory(model_id, provider_name, thinking_level)
    task_run = await adapter.invoke(input="123 + 321 = ?")

    _dump_paid_test_output(request, task_run=task_run)
    assert task_run.trace is not None, "Task run trace is None"
    assert len(task_run.trace) > 0, "Task run trace is empty"
    assert "444" in task_run.output.output, (
        f"Expected 444 in output: {task_run.output.output}"
    )


@pytest.mark.paid
@pytest.mark.parametrize("model_id,provider_name,thinking_level", STREAMING_MODELS)
async def test_invoke_openai_stream_with_prior_trace(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    adapter_factory: Callable[[str, ModelProviderName, str | None], LiteLlmAdapter],
):
    """Test that streaming works when continuing an existing run (session continuation)."""
    adapter = adapter_factory(model_id, provider_name, thinking_level)

    initial_run = await adapter.invoke(input="123 + 321 = ?")
    assert initial_run.trace is not None
    assert len(initial_run.trace) > 0

    continuation_chunks: list[litellm.ModelResponseStream] = []
    async for chunk in adapter.invoke_openai_stream(
        input="What was the result? Reply in one short sentence.",
        prior_trace=initial_run.trace,
    ):
        continuation_chunks.append(chunk)

    _dump_paid_test_output(request, continuation_chunks=continuation_chunks)
    assert len(continuation_chunks) > 0, "No continuation chunks collected"
