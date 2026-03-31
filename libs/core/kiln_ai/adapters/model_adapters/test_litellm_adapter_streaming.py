import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, patch

import litellm
import pytest
from litellm.types.utils import ChatCompletionDeltaToolCall

from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.adapters.model_adapters.stream_events import (
    AiSdkEventType,
    AiSdkStreamEvent,
    FinishEvent,
)
from kiln_ai.adapters.model_adapters.test_adapter_stream import (
    FakeStreamingCompletion,
    _make_model_response,
    _make_streaming_chunk,
    _make_tool_call,
)
from kiln_ai.datamodel import Project, PromptGenerators, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import ExternalKilnTool

logger = logging.getLogger(__name__)

RETURN_ON_TOOL_CALL_MODELS = [
    ("claude_4_5_haiku", ModelProviderName.anthropic, "medium"),
    ("claude_4_5_haiku", ModelProviderName.openrouter, "medium"),
    ("claude_4_5_haiku", ModelProviderName.openrouter, "none"),
    ("minimax_m2_5", ModelProviderName.openrouter, "medium"),
]

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
def task_external_sdk_only(tmp_path):
    """Task that instructs the model to use only the SDK external multiply tool (no registry tools)."""
    project_path: Path = tmp_path / "test_project_ext_sdk" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    task = Task(
        name="External SDK Tool Task",
        instruction=(
            "You must use the sdk_external_multiply tool to compute 3 times 7. "
            "Do not compute the product yourself. After you receive the tool result, "
            "write one short sentence about a cat that includes the numeric result."
        ),
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def task_structured(tmp_path):
    project_path: Path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    schema = {
        "type": "object",
        "properties": {
            "result": {"type": "integer"},
            "sentence": {"type": "string"},
        },
        "required": ["result", "sentence"],
    }
    task = Task(
        name="Structured Streaming Test Task",
        instruction="Solve the math problem using the provided tools. Return JSON with 'result' (the integer answer) and 'sentence' (a short sentence about a cat going to the mall that uses the result). Use the tools for all math.",
        parent=project,
        output_json_schema=json.dumps(schema),
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
        logger.info(f"AI SDK event: {event.type} {event.model_dump()}")

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

    text_deltas = [e.delta for e in events if e.type == AiSdkEventType.TEXT_DELTA]
    full_text = "".join(text_deltas)
    assert len(full_text) > 0, "Text content is empty"

    tool_input_available = [
        e for e in events if e.type == AiSdkEventType.TOOL_INPUT_AVAILABLE
    ]
    assert len(tool_input_available) >= 1, (
        "Should have at least one tool-input-available"
    )
    tool_input = tool_input_available[0].input
    assert "a" in tool_input and "b" in tool_input, (
        f"Tool input should have a and b keys: {tool_input}"
    )

    tool_output_available = [
        e for e in events if e.type == AiSdkEventType.TOOL_OUTPUT_AVAILABLE
    ]
    assert len(tool_output_available) >= 1, (
        "Should have at least one tool-output-available"
    )
    assert tool_output_available[0].output is not None, "Tool output should not be None"


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
            text_ids_seen.append(event.id)

        elif event.type == AiSdkEventType.TEXT_END:
            assert text_open, "text-end emitted without a preceding text-start"
            text_open = False

        elif event.type == AiSdkEventType.TEXT_DELTA:
            assert text_open, (
                f"text-delta emitted outside an open text block: {event.model_dump()}"
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


def _assert_completed_tool_trace(
    trace: list,
    expected_tool_call_ids: list[str],
) -> None:
    """Verify a completed trace has assistant+tool_calls, tool responses, and a final answer."""
    roles = [m.get("role") for m in trace]

    # There must be at least one assistant message with tool_calls followed by
    # tool response(s) and then a final assistant message.
    assert "tool" in roles, "Trace must contain at least one tool response message"

    # Every expected tool_call_id must appear in a role=tool message.
    tool_msgs = [m for m in trace if m.get("role") == "tool"]
    tool_msg_ids = [m.get("tool_call_id") for m in tool_msgs]
    for tc_id in expected_tool_call_ids:
        assert tc_id in tool_msg_ids, (
            f"tool_call_id {tc_id!r} missing from trace tool messages; found {tool_msg_ids}"
        )

    # The message immediately before each tool message must be an assistant
    # message with tool_calls that includes the matching id.
    for tool_msg in tool_msgs:
        tc_id = tool_msg.get("tool_call_id")
        idx = trace.index(tool_msg)
        # Find the nearest preceding assistant message with tool_calls.
        preceding_assistant = next(
            (
                trace[i]
                for i in range(idx - 1, -1, -1)
                if trace[i].get("role") == "assistant" and trace[i].get("tool_calls")
            ),
            None,
        )
        assert preceding_assistant is not None, (
            f"No assistant+tool_calls message found before tool message with id {tc_id!r}"
        )
        assistant_tc_ids = [
            tc["id"] for tc in preceding_assistant.get("tool_calls", [])
        ]
        assert tc_id in assistant_tc_ids, (
            f"tool_call_id {tc_id!r} not in preceding assistant tool_calls: {assistant_tc_ids}"
        )

    # The final message must be an assistant message with non-empty content
    # (the model's final answer).
    final_msg = trace[-1]
    assert final_msg.get("role") == "assistant", (
        f"Last trace message should be assistant, got {final_msg.get('role')!r}"
    )
    assert (
        final_msg.get("tool_calls") is None or len(final_msg.get("tool_calls", [])) == 0
    ), "Last trace message should not have tool_calls (should be final answer)"
    assert final_msg.get("content"), (
        "Last trace message (final answer) should have non-empty content"
    )


def _execute_tool_call(tool_call: dict) -> str:
    """Compute a built-in math tool call and return the string result."""
    name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"]["arguments"])
    a, b = float(args.get("a", 0)), float(args.get("b", 0))
    if name == "add":
        result = a + b
    elif name == "subtract":
        result = a - b
    elif name == "multiply":
        result = a * b
    elif name == "divide":
        result = a / b
    elif name == "sdk_external_multiply":
        result = a * b
    else:
        raise ValueError(f"Unknown tool: {name}")
    return str(int(result)) if result == int(result) else str(result)


def _sdk_external_multiply_tool() -> ExternalKilnTool:
    return ExternalKilnTool(
        tool_id="mcp::local::kiln_test_ext::sdk_external_multiply",
        name="sdk_external_multiply",
        description="Multiply two numbers. Use this tool for all arithmetic.",
        parameters_schema={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
    )


def _make_return_on_tool_call_adapter(
    task: Task,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
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
        base_adapter_config=AdapterConfig(return_on_tool_call=True),
    )


def _make_external_only_return_on_tool_call_adapter(
    task: Task,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
) -> LiteLlmAdapter:
    """Adapter with no Kiln registry tools; only external tool definitions in the request."""
    return LiteLlmAdapter(
        kiln_task=task,
        config=LiteLlmConfig(
            run_config_properties=KilnAgentRunConfigProperties(
                model_name=model_id,
                model_provider_name=provider_name,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=StructuredOutputMode.unknown,
                tools_config=None,
                thinking_level=thinking_level,
            )
        ),
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            external_tools=[_sdk_external_multiply_tool()],
        ),
    )


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name,thinking_level", RETURN_ON_TOOL_CALL_MODELS
)
async def test_invoke_with_return_on_tool_call_and_resume(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    task: Task,
):
    """invoke() with return_on_tool_call=True stops at tool calls; providing results resumes to a final answer."""
    adapter = _make_return_on_tool_call_adapter(
        task, model_id, provider_name, thinking_level
    )

    task_run = await adapter.invoke(input="3 * 7 = ?")
    _dump_paid_test_output(request, task_run_1=task_run)

    assert task_run.is_toolcall_pending, "Expected task_run to have pending tool calls"
    assert task_run.trace is not None

    last_msg = task_run.trace[-1]
    assert last_msg.get("role") == "assistant"
    pending_tool_calls = last_msg.get("tool_calls", [])
    assert len(pending_tool_calls) > 0, "Expected at least one pending tool call"

    tool_results = [
        {"tool_call_id": tc["id"], "content": _execute_tool_call(tc)}
        for tc in pending_tool_calls
    ]

    task_run2 = await adapter.invoke(input=tool_results, prior_trace=task_run.trace)
    _dump_paid_test_output(request, task_run_2=task_run2)

    assert not task_run2.is_toolcall_pending, "Expected task_run2 to be complete"
    assert "21" in task_run2.output.output, (
        f"Expected '21' in output: {task_run2.output.output}"
    )

    assert task_run2.trace is not None
    expected_ids = [tr["tool_call_id"] for tr in tool_results]
    _assert_completed_tool_trace(task_run2.trace, expected_ids)


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name,thinking_level", RETURN_ON_TOOL_CALL_MODELS
)
async def test_invoke_external_tools_only_return_on_tool_call_and_resume(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    task_external_sdk_only: Task,
):
    """invoke() with only external SDK tool definitions (no registry tools): model calls sdk_external_multiply; caller resumes."""
    adapter = _make_external_only_return_on_tool_call_adapter(
        task_external_sdk_only, model_id, provider_name, thinking_level
    )

    task_run = await adapter.invoke(input="Begin.")
    _dump_paid_test_output(request, task_run_1=task_run)

    assert task_run.is_toolcall_pending, "Expected task_run to have pending tool calls"
    assert task_run.trace is not None

    last_msg = task_run.trace[-1]
    assert last_msg.get("role") == "assistant"
    pending_tool_calls = last_msg.get("tool_calls", [])
    assert len(pending_tool_calls) > 0, "Expected at least one pending tool call"

    tool_names = [tc["function"]["name"] for tc in pending_tool_calls]
    assert "sdk_external_multiply" in tool_names, (
        f"Expected sdk_external_multiply in {tool_names!r}"
    )

    tool_results = [
        {"tool_call_id": tc["id"], "content": _execute_tool_call(tc)}
        for tc in pending_tool_calls
    ]

    task_run2 = await adapter.invoke(input=tool_results, prior_trace=task_run.trace)
    _dump_paid_test_output(request, task_run_2=task_run2)

    assert not task_run2.is_toolcall_pending, "Expected task_run2 to be complete"
    assert "21" in task_run2.output.output, (
        f"Expected '21' in output: {task_run2.output.output}"
    )

    assert task_run2.trace is not None
    expected_ids = [tr["tool_call_id"] for tr in tool_results]
    _assert_completed_tool_trace(task_run2.trace, expected_ids)


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name,thinking_level", RETURN_ON_TOOL_CALL_MODELS
)
async def test_ai_sdk_stream_with_return_on_tool_call_and_resume(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    task: Task,
):
    """AI SDK stream with return_on_tool_call=True emits finishReason='tool-calls'; resuming with results completes normally."""
    adapter = _make_return_on_tool_call_adapter(
        task, model_id, provider_name, thinking_level
    )

    first_stream = adapter.invoke_ai_sdk_stream(input="3 * 7 = ?")
    events_1: list[AiSdkStreamEvent] = []
    async for event in first_stream:
        events_1.append(event)

    _dump_paid_test_output(request, events_1=events_1)

    finish_events_1 = [e for e in events_1 if e.type == AiSdkEventType.FINISH]
    assert len(finish_events_1) == 1, "Should have exactly one FINISH event"
    finish_1 = finish_events_1[0]
    assert isinstance(finish_1, FinishEvent)
    finish_reason_1 = (
        finish_1.messageMetadata.finishReason if finish_1.messageMetadata else None
    )
    assert finish_reason_1 == "tool-calls", (
        f"Expected finishReason 'tool-calls', got {finish_reason_1!r}"
    )

    task_run_1 = first_stream.task_run
    assert task_run_1.is_toolcall_pending
    assert task_run_1.trace is not None

    last_msg = task_run_1.trace[-1]
    pending_tool_calls = last_msg.get("tool_calls", [])
    assert len(pending_tool_calls) > 0

    tool_results = [
        {"tool_call_id": tc["id"], "content": _execute_tool_call(tc)}
        for tc in pending_tool_calls
    ]

    second_stream = adapter.invoke_ai_sdk_stream(
        input=tool_results, prior_trace=task_run_1.trace
    )
    events_2: list[AiSdkStreamEvent] = []
    async for event in second_stream:
        events_2.append(event)

    _dump_paid_test_output(request, events_2=events_2)

    finish_events_2 = [e for e in events_2 if e.type == AiSdkEventType.FINISH]
    assert len(finish_events_2) == 1, (
        "Should have exactly one FINISH event in second stream"
    )
    finish_2 = finish_events_2[0]
    assert isinstance(finish_2, FinishEvent)
    finish_reason_2 = (
        finish_2.messageMetadata.finishReason if finish_2.messageMetadata else None
    )
    assert finish_reason_2 == "stop", (
        f"Expected finishReason 'stop', got {finish_reason_2!r}"
    )

    task_run_2 = second_stream.task_run
    assert not task_run_2.is_toolcall_pending
    assert "21" in task_run_2.output.output, (
        f"Expected '21' in output: {task_run_2.output.output}"
    )

    assert task_run_2.trace is not None
    expected_ids = [tr["tool_call_id"] for tr in tool_results]
    _assert_completed_tool_trace(task_run_2.trace, expected_ids)


def _make_structured_return_on_tool_call_adapter(
    task: Task,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
) -> LiteLlmAdapter:
    return LiteLlmAdapter(
        kiln_task=task,
        config=LiteLlmConfig(
            run_config_properties=KilnAgentRunConfigProperties(
                model_name=model_id,
                model_provider_name=provider_name,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=StructuredOutputMode.json_schema,
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
        base_adapter_config=AdapterConfig(return_on_tool_call=True),
    )


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_id,provider_name,thinking_level", RETURN_ON_TOOL_CALL_MODELS
)
async def test_invoke_structured_output_with_return_on_tool_call_and_resume(
    request: pytest.FixtureRequest,
    model_id: str,
    provider_name: ModelProviderName,
    thinking_level: str | None,
    task_structured: Task,
):
    """Structured output task: invoke() with return_on_tool_call=True stops at tool calls; resuming produces a valid JSON final answer."""
    adapter = _make_structured_return_on_tool_call_adapter(
        task_structured, model_id, provider_name, thinking_level
    )

    task_run = await adapter.invoke(input="3 * 7 = ?")
    _dump_paid_test_output(request, task_run_1=task_run)

    assert task_run.is_toolcall_pending, "Expected task_run to have pending tool calls"
    assert task_run.trace is not None

    last_msg = task_run.trace[-1]
    assert last_msg.get("role") == "assistant"
    pending_tool_calls = last_msg.get("tool_calls", [])
    assert len(pending_tool_calls) > 0, "Expected at least one pending tool call"

    tool_results = [
        {"tool_call_id": tc["id"], "content": _execute_tool_call(tc)}
        for tc in pending_tool_calls
    ]

    task_run2 = await adapter.invoke(input=tool_results, prior_trace=task_run.trace)
    _dump_paid_test_output(request, task_run_2=task_run2)

    assert not task_run2.is_toolcall_pending, "Expected task_run2 to be complete"
    output = json.loads(task_run2.output.output)
    assert isinstance(output, dict), (
        f"Expected dict output for structured task, got {type(output)}: {output}"
    )
    assert output.get("result") == 21, f"Expected result=21, got {output.get('result')}"
    assert "sentence" in output, f"'sentence' key missing from output: {output}"

    assert task_run2.trace is not None
    expected_ids = [tr["tool_call_id"] for tr in tool_results]
    _assert_completed_tool_trace(task_run2.trace, expected_ids)


# ── Mocked variants (CI-friendly, no real API calls) ──────────────────────────


def _make_mocked_adapter(task: Task, structured: bool = False) -> LiteLlmAdapter:
    """Create a LiteLlmAdapter backed by openai_compatible for use with mocked API calls."""
    return LiteLlmAdapter(
        kiln_task=task,
        config=LiteLlmConfig(
            base_url="http://localhost:11434",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="test-model",
                model_provider_name=ModelProviderName.openai_compatible,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=(
                    StructuredOutputMode.json_schema
                    if structured
                    else StructuredOutputMode.unknown
                ),
                tools_config=ToolsRunConfig(
                    tools=[
                        KilnBuiltInToolId.ADD_NUMBERS,
                        KilnBuiltInToolId.SUBTRACT_NUMBERS,
                        KilnBuiltInToolId.MULTIPLY_NUMBERS,
                        KilnBuiltInToolId.DIVIDE_NUMBERS,
                    ],
                ),
            ),
        ),
        base_adapter_config=AdapterConfig(return_on_tool_call=True),
    )


async def test_mocked_invoke_return_on_tool_call_and_resume(task: Task):
    """Mocked (CI-safe) variant of test_invoke_with_return_on_tool_call_and_resume."""
    adapter = _make_mocked_adapter(task)

    tool_call = _make_tool_call(
        call_id="call_mock_multiply",
        name="multiply",
        arguments={"a": 3, "b": 7},
    )
    tool_call_response = _make_model_response(content=None, tool_calls=[tool_call])
    final_response = _make_model_response(
        content="3 multiplied by 7 is 21. A cat went to the mall and bought 21 items."
    )
    responses = [
        (tool_call_response, tool_call_response.choices[0]),
        (final_response, final_response.choices[0]),
    ]

    with patch.object(
        LiteLlmAdapter,
        "acompletion_checking_response",
        new=AsyncMock(side_effect=responses),
    ):
        task_run = await adapter.invoke(input="3 * 7 = ?")

        assert task_run.is_toolcall_pending, (
            "Expected task_run to have pending tool calls"
        )
        assert task_run.trace is not None
        last_msg = task_run.trace[-1]
        assert last_msg.get("role") == "assistant"
        pending_tool_calls = last_msg.get("tool_calls", [])
        assert len(pending_tool_calls) == 1
        assert pending_tool_calls[0]["id"] == "call_mock_multiply"

        tool_results = [
            {"tool_call_id": tc["id"], "content": "21"} for tc in pending_tool_calls
        ]

        task_run2 = await adapter.invoke(input=tool_results, prior_trace=task_run.trace)

    assert not task_run2.is_toolcall_pending
    assert "21" in task_run2.output.output
    assert task_run2.trace is not None
    _assert_completed_tool_trace(task_run2.trace, ["call_mock_multiply"])


async def test_mocked_ai_sdk_stream_return_on_tool_call_and_resume(task: Task):
    """Mocked (CI-safe) variant of test_ai_sdk_stream_with_return_on_tool_call_and_resume."""
    adapter = _make_mocked_adapter(task)

    tool_call = _make_tool_call(
        call_id="call_mock_multiply",
        name="multiply",
        arguments={"a": 3, "b": 7},
    )
    tool_call_response = _make_model_response(content=None, tool_calls=[tool_call])
    first_fake_stream = FakeStreamingCompletion(
        tool_call_response,
        [_make_streaming_chunk(finish_reason="tool_calls")],
    )

    final_response = _make_model_response(
        content="3 multiplied by 7 is 21. A cat went to the mall and bought 21 items."
    )
    second_fake_stream = FakeStreamingCompletion(final_response)

    with patch(
        "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
        return_value=first_fake_stream,
    ):
        first_stream = adapter.invoke_ai_sdk_stream(input="3 * 7 = ?")
        events_1: list[AiSdkStreamEvent] = []
        async for event in first_stream:
            events_1.append(event)

    finish_events_1 = [e for e in events_1 if e.type == AiSdkEventType.FINISH]
    assert len(finish_events_1) == 1
    fe1 = finish_events_1[0]
    assert isinstance(fe1, FinishEvent)
    assert fe1.messageMetadata is not None
    assert fe1.messageMetadata.finishReason == "tool-calls"

    task_run_1 = first_stream.task_run
    assert task_run_1.is_toolcall_pending
    pending_tool_calls = task_run_1.trace[-1].get("tool_calls", [])
    assert len(pending_tool_calls) == 1
    tool_results = [
        {"tool_call_id": tc["id"], "content": "21"} for tc in pending_tool_calls
    ]

    with patch(
        "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
        return_value=second_fake_stream,
    ):
        second_stream = adapter.invoke_ai_sdk_stream(
            input=tool_results, prior_trace=task_run_1.trace
        )
        events_2: list[AiSdkStreamEvent] = []
        async for event in second_stream:
            events_2.append(event)

    finish_events_2 = [e for e in events_2 if e.type == AiSdkEventType.FINISH]
    assert len(finish_events_2) == 1
    fe2 = finish_events_2[0]
    assert isinstance(fe2, FinishEvent)
    assert fe2.messageMetadata is not None
    assert fe2.messageMetadata.finishReason == "stop"

    task_run_2 = second_stream.task_run
    assert not task_run_2.is_toolcall_pending
    assert "21" in task_run_2.output.output
    _assert_completed_tool_trace(task_run_2.trace, ["call_mock_multiply"])


async def test_mocked_invoke_structured_output_with_return_on_tool_call_and_resume(
    task_structured: Task,
):
    """Mocked (CI-safe) variant of test_invoke_structured_output_with_return_on_tool_call_and_resume."""
    adapter = _make_mocked_adapter(task_structured, structured=True)

    tool_call = _make_tool_call(
        call_id="call_mock_multiply",
        name="multiply",
        arguments={"a": 3, "b": 7},
    )
    tool_call_response = _make_model_response(content=None, tool_calls=[tool_call])
    final_response = _make_model_response(
        content='{"result": 21, "sentence": "A cat went to the mall and bought 21 items."}'
    )
    responses = [
        (tool_call_response, tool_call_response.choices[0]),
        (final_response, final_response.choices[0]),
    ]

    with patch.object(
        LiteLlmAdapter,
        "acompletion_checking_response",
        new=AsyncMock(side_effect=responses),
    ):
        task_run = await adapter.invoke(input="3 * 7 = ?")

        assert task_run.is_toolcall_pending
        pending_tool_calls = task_run.trace[-1].get("tool_calls", [])
        assert len(pending_tool_calls) == 1

        tool_results = [
            {"tool_call_id": tc["id"], "content": "21"} for tc in pending_tool_calls
        ]

        task_run2 = await adapter.invoke(input=tool_results, prior_trace=task_run.trace)

    assert not task_run2.is_toolcall_pending
    output = json.loads(task_run2.output.output)
    assert output.get("result") == 21
    assert "sentence" in output

    _assert_completed_tool_trace(task_run2.trace, ["call_mock_multiply"])
