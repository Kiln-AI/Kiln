"""Paid integration test: per-message usage flows through real multi-turn
chat sessions with tool calls.

Verifies, end-to-end against GLM 5.1 on Fireworks, that:

1. Every assistant message in a TaskRun's trace carries its own per-call
   usage (input / output / total / cost).
2. ``TaskRun.usage`` equals the sum of per-message usage on the messages
   produced by **this** run (i.e. excludes any seeded prior trace).
3. ``TaskRun.cumulative_usage`` equals the sum of per-message usage across
   the **full** trace (seeded prior trace + new messages).
4. Multi-step problems that require multiple inference calls inside a
   single ``return_on_tool_call=False`` turn keep all per-call usages
   (not just the last call's).
5. A ``return_on_tool_call=True`` interrupt followed by a resume with
   ``input=tool_result_dict + prior_trace=...`` carries the prior assistant
   message's usage forward.

Pinpoints whether token counts are being lost across multiturn + tool
calls — exactly the back-and-forth chat scenario.

Run::

    pytest libs/core/kiln_ai/adapters/model_adapters/test_multiturn_usage_paid.py --runpaid
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from litellm.types.utils import ChatCompletionMessageToolCall, Function

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.test_paid_utils import (
    skip_if_missing_provider_keys,
)
from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.usage import MessageUsage
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

MODEL_NAME = "glm_5_1"
PROVIDER = ModelProviderName.fireworks_ai


def _build_math_task(tmp_path: Path) -> datamodel.Task:
    project = datamodel.Project(name="usage_test", path=tmp_path / "p.kiln")
    project.save_to_file()
    task = datamodel.Task(
        parent=project,
        name="math",
        instruction=(
            "You are a calculator that uses the provided tools (add, subtract, "
            "multiply, divide) for every math operation. Do not compute "
            "manually. End your final response with the answer in square "
            "brackets, e.g., [42]."
        ),
    )
    task.save_to_file()
    return task


def _adapter(task: datamodel.Task, *, return_on_tool_call: bool = False):
    return adapter_for_task(
        task,
        run_config_properties=KilnAgentRunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_instructions,
            model_name=MODEL_NAME,
            model_provider_name=PROVIDER,
            prompt_id="simple_prompt_builder",
        ),
        base_adapter_config=AdapterConfig(return_on_tool_call=return_on_tool_call),
    )


def _assistant_messages(trace) -> list[dict]:
    assert trace is not None
    return [m for m in trace if isinstance(m, dict) and m.get("role") == "assistant"]


def _coerce_usage(raw) -> MessageUsage | None:
    """Trace messages may carry usage as a ``MessageUsage`` instance or as a
    dict (post-JSON round-trip). Normalize."""
    if raw is None:
        return None
    if isinstance(raw, MessageUsage):
        return raw
    if isinstance(raw, dict):
        return MessageUsage.model_validate(raw)
    raise TypeError(f"Unexpected usage type on trace message: {type(raw)}")


def _assert_all_assistants_have_usage(trace) -> None:
    """Every assistant message in the trace must have a non-None usage with
    real provider-reported token counts (input, output, total, cached).
    ``cost`` is allowed to be ``None`` — providers don't always report it,
    and LiteLLM's cost-resolution table can lag behind newer models."""
    assistants = _assistant_messages(trace)
    assert len(assistants) >= 1, f"trace contains no assistant messages at all: {trace}"
    for i, m in enumerate(assistants):
        usage = _coerce_usage(m.get("usage"))
        assert usage is not None, (
            f"assistant message #{i} in trace is missing a `usage` field "
            f"entirely — provider reported tokens but they weren't attached. "
            f"Message: {m}"
        )
        assert usage.input_tokens is not None and usage.input_tokens > 0, (
            f"assistant message #{i} has no input_tokens on its usage: {usage}"
        )
        assert usage.output_tokens is not None and usage.output_tokens > 0, (
            f"assistant message #{i} has no output_tokens on its usage: {usage}"
        )
        assert usage.total_tokens is not None and usage.total_tokens > 0, (
            f"assistant message #{i} has no total_tokens on its usage: {usage}"
        )
        # Fireworks reports total_tokens = input + output. We don't strictly
        # require equality (some providers add reasoning tokens etc.), but
        # total must at least be ≥ input + output.
        assert usage.total_tokens >= usage.input_tokens + usage.output_tokens, (
            f"assistant message #{i} total_tokens ({usage.total_tokens}) is "
            f"smaller than input + output ({usage.input_tokens} + "
            f"{usage.output_tokens}) — the provider's reported total looks "
            f"truncated."
        )
        assert usage.cached_tokens is not None and usage.cached_tokens >= 0, (
            f"assistant message #{i} has no cached_tokens on its usage: {usage}. "
            f"Expected the adapter to populate the field with the provider's "
            f"reported cached-prompt-tokens count (0 if no cache hit)."
        )
        # cost is allowed to be None (or 0.0) — providers don't always
        # report it, and LiteLLM's cost-resolution table can lag behind
        # newer models. Only fail on negative values.
        if usage.cost is not None:
            assert usage.cost >= 0, (
                f"assistant message #{i} has negative cost: {usage.cost}"
            )


def _assert_last_trace_has_usage_on_every_assistant(last_run: TaskRun) -> None:
    """Dedicated check for the FINAL TaskRun in a chain: every assistant
    message in its trace must carry a non-None ``usage`` with the required
    fields populated.

    The last trace is the canonical "full conversation history" snapshot
    that downstream consumers (UI, eval, billing dashboards) read. If any
    assistant message in it is missing per-message usage, the consumer
    sees that inference's tokens as zero — silent undercount.

    This exists as a separate explicit check (in addition to
    ``_assert_per_message_usage_chain_consistent`` which walks every run)
    so a failure here points unambiguously at the final-snapshot path."""
    assert last_run.trace is not None, "last TaskRun has no trace"
    last_assistants = _assistant_messages(last_run.trace)
    assert len(last_assistants) >= 1, (
        f"last TaskRun's trace has no assistant messages: {last_run.trace}"
    )
    missing: list[int] = []
    for i, m in enumerate(last_assistants):
        if _coerce_usage(m.get("usage")) is None:
            missing.append(i)
    assert not missing, (
        f"Last TaskRun's trace is missing `usage` on assistant message(s) "
        f"at index(es) {missing} (out of {len(last_assistants)} total "
        f"assistants). Every assistant turn in the final snapshot must "
        f"carry per-message usage."
    )
    # Now apply the full per-field shape requirements to the last trace.
    _assert_all_assistants_have_usage(last_run.trace)


def _assert_last_trace_anchors_each_taskrun_usage(
    full_chain: list[TaskRun],
) -> None:
    """When ``return_on_tool_call=True``, every adapter invoke produces
    exactly one new assistant message — the one whose tool call (or final
    content) ended that invoke. So the FINAL TaskRun's trace must contain
    assistant messages, in order, whose per-message usage matches each
    TaskRun's `usage` one-to-one.

    This is the strongest possible check: not just "the totals add up" but
    "every individual TaskRun's contribution shows up at the right slot in
    the final trace, with the exact tokens/cost it reported."
    """
    assert full_chain, "expected at least one TaskRun in the chain"
    last_trace = full_chain[-1].trace
    assert last_trace is not None, "last TaskRun has no trace"

    last_assistants = _assistant_messages(last_trace)
    assert len(last_assistants) == len(full_chain), (
        f"With return_on_tool_call=True, the last trace should contain exactly "
        f"one assistant message per TaskRun in the chain "
        f"({len(full_chain)} expected) — got {len(last_assistants)}. Either "
        f"some assistant message was lost on a resume, or the test setup "
        f"isn't actually using return_on_tool_call=True."
    )

    for idx, (assistant_msg, run) in enumerate(zip(last_assistants, full_chain)):
        msg_usage = _coerce_usage(assistant_msg.get("usage"))
        assert msg_usage is not None, (
            f"assistant message #{idx} in the last trace has no usage"
        )
        assert run.usage is not None, f"run #{idx} has no usage"
        for field in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_tokens",
        ):
            assert getattr(msg_usage, field) == getattr(run.usage, field), (
                f"assistant message #{idx} in the LAST trace has "
                f"{field}={getattr(msg_usage, field)}, but run #{idx} reported "
                f"usage.{field}={getattr(run.usage, field)}. The trace is "
                f"missing or has a stale value for this inference call."
            )
        # Cost may have float wobble; allow epsilon.
        if msg_usage.cost is not None and run.usage.cost is not None:
            assert msg_usage.cost == pytest.approx(run.usage.cost), (
                f"assistant message #{idx} usage.cost ({msg_usage.cost}) != "
                f"run #{idx} usage.cost ({run.usage.cost})"
            )


@pytest.mark.paid
async def test_multiturn_with_internal_tool_loop_preserves_per_message_usage(tmp_path):
    """Multi-step problem forces multiple inference calls inside one
    ``return_on_tool_call=False`` turn (model → tool → model → tool → model).
    Then a follow-up question continues the chat. Across both invocations
    every assistant message gets per-message usage, ``TaskRun.usage`` equals
    the sum of THIS run's new per-message usages, and ``cumulative_usage``
    on the second run equals the sum across the FULL trace including the
    seeded prior turn."""
    skip_if_missing_provider_keys(PROVIDER)
    task = _build_math_task(tmp_path)
    adapter = _adapter(task, return_on_tool_call=False)

    math_tools = [AddTool(), SubtractTool(), MultiplyTool(), DivideTool()]
    with patch.object(adapter, "available_tools", return_value=math_tools):
        # Round 1: multi-step problem. Should force 2+ inferences inside the
        # internal tool loop (one inference asks for add, then another asks
        # for multiply, then a final one returns the answer).
        run1 = await adapter.invoke("Compute four plus six, then multiply by ten.")

        # Round 2: continue the conversation with a follow-up question that
        # references the prior result.
        run2 = await adapter.invoke(
            "Now divide that result by 2.",
            prior_trace=run1.trace,
        )

    # ─── Run 1: fresh, multi-inference ──────────────────────────────────────
    assert run1.trace is not None
    assistants_run1 = _assistant_messages(run1.trace)
    assert len(assistants_run1) >= 2, (
        f"Expected at least two assistant messages in run1 (one or more "
        f"tool-call rounds + final answer), got {len(assistants_run1)}. "
        f"Trace: {run1.trace}"
    )
    _assert_all_assistants_have_usage(run1.trace)

    # ``TaskRun.usage`` MUST equal the sum of all per-message usage on
    # run1's trace (run1 is fresh — no seeded contributions). Failure here
    # means an inference call's usage was added to the running aggregator
    # but not to the per-message dict, OR vice versa, OR overwrites are
    # happening on the per-message keying.
    sum_run1 = MessageUsage.from_trace(run1.trace)
    assert run1.usage is not None
    assert run1.usage.input_tokens == sum_run1.input_tokens, (
        f"run1.usage.input_tokens ({run1.usage.input_tokens}) != sum of per-message "
        f"input_tokens ({sum_run1.input_tokens}). One or more inference calls "
        f"are not being counted on either the running aggregator or the trace."
    )
    assert run1.usage.output_tokens == sum_run1.output_tokens, (
        f"run1.usage.output_tokens ({run1.usage.output_tokens}) != sum "
        f"({sum_run1.output_tokens})"
    )
    if run1.usage.cost is not None and sum_run1.cost is not None:
        assert run1.usage.cost == pytest.approx(sum_run1.cost), (
            f"run1.usage.cost ({run1.usage.cost}) != sum ({sum_run1.cost})"
        )

    # cumulative_usage on a fresh run = same sum.
    assert run1.cumulative_usage is not None
    assert run1.cumulative_usage.input_tokens == sum_run1.input_tokens
    assert run1.cumulative_usage.output_tokens == sum_run1.output_tokens

    # ─── Run 2: seeded continuation ─────────────────────────────────────────
    assert run2.trace is not None
    assistants_run2 = _assistant_messages(run2.trace)
    assert len(assistants_run2) > len(assistants_run1), (
        f"run2 trace should include all run1 assistants ({len(assistants_run1)}) "
        f"plus at least one new assistant message — got {len(assistants_run2)}"
    )
    _assert_all_assistants_have_usage(run2.trace)

    # cumulative_usage on run2 = sum across the FULL trace (seeded + new).
    sum_run2_full = MessageUsage.from_trace(run2.trace)
    assert run2.cumulative_usage is not None
    assert run2.cumulative_usage.input_tokens == sum_run2_full.input_tokens, (
        f"run2.cumulative_usage.input_tokens ({run2.cumulative_usage.input_tokens}) "
        f"!= sum of per-message input_tokens across the full trace "
        f"({sum_run2_full.input_tokens})"
    )

    # The seeded prior trace's usage MUST contribute. cumulative > usage.
    assert run2.usage is not None
    assert run2.cumulative_usage.input_tokens > run2.usage.input_tokens, (
        f"run2.cumulative_usage.input_tokens ({run2.cumulative_usage.input_tokens}) "
        f"is not strictly greater than run2.usage.input_tokens "
        f"({run2.usage.input_tokens}). This means the seeded prior trace's "
        f"per-message usage was lost between turns — the canonical "
        f"multiturn-undercount bug."
    )

    # And explicitly: cumulative on run2 = run1.cumulative + run2.usage.
    expected_cum_input = (run1.cumulative_usage.input_tokens or 0) + (
        run2.usage.input_tokens or 0
    )
    assert run2.cumulative_usage.input_tokens == expected_cum_input, (
        f"run2.cumulative_usage.input_tokens ({run2.cumulative_usage.input_tokens}) "
        f"should equal run1.cumulative_usage + run2.usage = {expected_cum_input}"
    )

    # Final-snapshot check: the LAST run's trace (the conversation history a
    # consumer would render) carries per-message usage on every assistant.
    _assert_last_trace_has_usage_on_every_assistant(run2)


@pytest.mark.paid
async def test_return_on_tool_call_resume_preserves_per_message_usage(tmp_path):
    """``return_on_tool_call=True``: adapter exits after the first inference
    that asks for a tool. Caller resumes with the tool result via
    ``input={"tool_call_id": ..., "content": "..."}`` and ``prior_trace``.
    Across both invocations every assistant message has its own per-message
    usage and run2.cumulative_usage = run1.usage + run2.usage."""
    skip_if_missing_provider_keys(PROVIDER)
    task = _build_math_task(tmp_path)
    adapter = _adapter(task, return_on_tool_call=True)

    math_tools = [AddTool(), SubtractTool(), MultiplyTool(), DivideTool()]
    with patch.object(adapter, "available_tools", return_value=math_tools):
        # Round 1: should exit on the first tool call (the model asks for
        # multiply, adapter returns control to the caller).
        run1 = await adapter.invoke("Compute 3 multiplied by 7.")

    assert run1.is_toolcall_pending, (
        "Expected run1 to exit with a pending tool call "
        "(return_on_tool_call=True). The model didn't request a tool — "
        "this test only covers the tool-call-interrupt path."
    )
    assert run1.trace is not None
    assistants_run1 = _assistant_messages(run1.trace)
    assert len(assistants_run1) == 1, (
        f"Expected exactly one assistant message before tool-call interrupt, "
        f"got {len(assistants_run1)}"
    )
    _assert_all_assistants_have_usage(run1.trace)

    # The interrupting assistant message has the tool call we need to satisfy.
    last_msg = run1.trace[-1]
    assert isinstance(last_msg, dict)
    tool_calls = last_msg.get("tool_calls") or []
    assert len(tool_calls) >= 1, "expected at least one pending tool call"
    tc = tool_calls[0]
    tc_id = tc["id"]

    # Caller "executes" the tool externally (3 * 7 = 21).
    tool_result_input = {
        "tool_call_id": tc_id,
        "content": "21",
    }

    with patch.object(adapter, "available_tools", return_value=math_tools):
        # Round 2: resume with the tool result. The model should then return
        # a final answer.
        run2 = await adapter.invoke(
            input=tool_result_input,
            prior_trace=run1.trace,
        )

    assert not run2.is_toolcall_pending
    assert run2.trace is not None
    _assert_all_assistants_have_usage(run2.trace)

    # cumulative_usage on run2 must include run1's assistant message usage.
    assert run1.usage is not None
    assert run2.usage is not None
    assert run2.cumulative_usage is not None

    expected_cum_input = (run1.usage.input_tokens or 0) + (run2.usage.input_tokens or 0)
    assert run2.cumulative_usage.input_tokens == expected_cum_input, (
        f"run2.cumulative_usage.input_tokens ({run2.cumulative_usage.input_tokens}) "
        f"should equal run1.usage + run2.usage ({expected_cum_input}). A mismatch "
        f"means the seeded prior trace's per-message usage was lost on resume — "
        f"the multiturn-undercount bug for the return_on_tool_call flow."
    )
    assert run2.cumulative_usage.input_tokens > run2.usage.input_tokens, (
        "run2.cumulative_usage should strictly exceed run2.usage because the "
        "seeded prior trace contributes a non-zero number of input tokens."
    )

    # Final-snapshot check: the LAST run's trace (the conversation history a
    # consumer would render) carries per-message usage on every assistant.
    _assert_last_trace_has_usage_on_every_assistant(run2)


# ───────────────────────────────────────────────────────────────────────────
# Full chat back-and-forth: mirrors the chat backend's session loop in
# kiln_server/api/kiln_fastapi_api/chat/stream_orchestration.py:
# `return_on_tool_call=True` adapter; on each round, exhaust the call,
# execute pending tool calls server-side via `adapter.process_tool_calls`,
# resume with the tool messages as `input` and the previous trace as
# `prior_trace`. Repeat across multiple user messages.
#
# These tests exercise BOTH variants the user can drive the chat with:
# the synchronous `adapter.invoke(...)` and the streaming
# `adapter.invoke_ai_sdk_stream(...)` (which is what the production chat
# path actually uses).
# ───────────────────────────────────────────────────────────────────────────


def _convert_pending_tool_calls(
    task_run: TaskRun,
) -> list[ChatCompletionMessageToolCall]:
    """Mirror chat backend's `filter_convert_pending_tool_calls` + converter:
    pull the trailing assistant message's tool_calls (excluding any internal
    `task_response`) and rehydrate them into LiteLLM objects so
    `adapter.process_tool_calls` can run them."""
    trace = task_run.trace
    if not trace:
        return []
    last = trace[-1]
    if not isinstance(last, dict) or last.get("role") != "assistant":
        return []
    raw_calls: list[Any] = list(last.get("tool_calls") or [])
    out: list[ChatCompletionMessageToolCall] = []
    for tc in raw_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        name = fn.get("name")
        if name == "task_response":
            continue
        out.append(
            ChatCompletionMessageToolCall(
                id=str(tc["id"]),
                type="function",
                function=Function(name=name, arguments=fn.get("arguments", "")),
            )
        )
    return out


async def _drive_user_turn(
    adapter: LiteLlmAdapter,
    user_input: Any,
    *,
    prior_trace: list[ChatCompletionMessageParam] | None,
    math_tools: list,
    streaming: bool,
    max_rounds: int = 8,
) -> list[TaskRun]:
    """Drive one user message through the full back-and-forth loop until
    the model produces a final assistant message (no pending tool calls).
    Mirrors `_chat_sse_session_inner`'s round loop in the chat backend.

    Returns the chain of TaskRuns produced for this user turn (one per
    inference call). The caller is responsible for chaining these across
    multiple user messages by passing the latest TaskRun's trace as
    `prior_trace` on the next call."""
    runs: list[TaskRun] = []
    current_input = user_input
    current_prior = prior_trace
    for round_idx in range(max_rounds):
        with patch.object(adapter, "available_tools", return_value=math_tools):
            if streaming:
                stream = adapter.invoke_ai_sdk_stream(
                    input=current_input, prior_trace=current_prior
                )
                async for _ in stream:
                    pass
                run = stream.task_run
            else:
                run = await adapter.invoke(
                    input=current_input, prior_trace=current_prior
                )
            runs.append(run)
            if not run.is_toolcall_pending:
                return runs
            # Adapter handed control back to us with pending tool calls. Execute
            # them server-side via `adapter.process_tool_calls` (same call the
            # chat backend uses) and resume with the tool messages as input.
            pending = _convert_pending_tool_calls(run)
            assert len(pending) >= 1, (
                f"round {round_idx}: task_run.is_toolcall_pending is True "
                f"but no client-visible tool calls were extracted from the trace"
            )
            _, tool_msgs = await adapter.process_tool_calls(pending)
        current_input = list(tool_msgs)
        current_prior = run.trace
    raise RuntimeError(
        f"Hit max_rounds={max_rounds} without producing a final assistant "
        f"message. Likely a tool-call loop the model isn't terminating."
    )


def _assert_per_message_usage_chain_consistent(runs: list[TaskRun]) -> None:
    """Across an ordered chain of TaskRuns, assert:
    - every assistant message in every run's trace has a non-None per-message usage
    - each run's `cumulative_usage` equals the sum of every preceding run's
      `usage` plus its own `usage` (i.e. the chain's running total)
    - the latest run's `cumulative_usage.input_tokens` equals the sum of every
      run's `usage.input_tokens` (the canonical chat-undercount sentinel)"""
    assert runs, "expected at least one TaskRun in the chain"
    running_input = 0
    running_output = 0
    for idx, run in enumerate(runs):
        assert run.trace is not None, f"run {idx} has no trace"
        _assert_all_assistants_have_usage(run.trace)
        assert run.usage is not None, f"run {idx} has no usage"
        assert run.cumulative_usage is not None, f"run {idx} has no cumulative_usage"

        # cumulative_usage == sum-from-trace at the run's finalization time.
        sum_from_trace = MessageUsage.from_trace(run.trace)
        assert run.cumulative_usage.input_tokens == sum_from_trace.input_tokens, (
            f"run {idx}: cumulative_usage.input_tokens "
            f"({run.cumulative_usage.input_tokens}) != sum-from-trace "
            f"({sum_from_trace.input_tokens}) — `cumulative_usage` was not "
            f"recomputed correctly at finalization."
        )

        # Walk the chain: cumulative on run N = (sum of usage[0..N]).
        running_input += run.usage.input_tokens or 0
        running_output += run.usage.output_tokens or 0
        assert run.cumulative_usage.input_tokens == running_input, (
            f"run {idx}: cumulative_usage.input_tokens "
            f"({run.cumulative_usage.input_tokens}) != running sum across the "
            f"chain ({running_input}). Either prior trace's per-message usage "
            f"was lost on resume, or this run's usage isn't reflected in the "
            f"cumulative."
        )
        assert run.cumulative_usage.output_tokens == running_output, (
            f"run {idx}: cumulative_usage.output_tokens "
            f"({run.cumulative_usage.output_tokens}) != running sum "
            f"({running_output})"
        )


# A 10-message conversation chosen to mix conversational patterns:
#
# - Plain replies with no tool calls (greetings / confirmations) — exercises
#   the user→assistant path with NO tool-call back-and-forth.
# - Single-tool-round messages — exercises user→assistant→tool→assistant.
# - Multi-tool-round messages — exercises
#   user→assistant→tool→assistant→tool→assistant.
#
# We don't enforce specific patterns per message because models are
# non-deterministic; instead we assert that across the full chain we saw
# both kinds (≥1 plain reply, ≥4 tool rounds total).
_TEN_MESSAGE_CONVO: list[str] = [
    "Hi! Can you help me with some math questions today?",
    "Compute 5 + 3 using the add tool.",
    "Now multiply that result by 4.",
    "What is 10 minus 7?",
    "And subtract 1 from that.",
    "Compute (8 + 2) divided by 5. Show your steps.",
    "Add 100 to 50, then multiply that sum by 2.",
    "What is 7 times 6?",
    "Just to confirm: are you using the math tools for these computations?",
    "Final question — what is 9 + 1?",
]


async def _run_chat_session(streaming: bool, tmp_path: Path) -> None:
    """Drive a 10-user-message chat session against GLM 5.1 — mixing plain
    user→assistant exchanges with multi-tool-round back-and-forths.
    Verifies usage tracking across every TaskRun in the entire chain."""
    skip_if_missing_provider_keys(PROVIDER)
    task = _build_math_task(tmp_path)
    adapter = _adapter(task, return_on_tool_call=True)
    assert isinstance(adapter, LiteLlmAdapter), (
        "Expected a LiteLlmAdapter for fireworks_ai; the test relies on "
        "process_tool_calls being available."
    )
    math_tools = [AddTool(), SubtractTool(), MultiplyTool(), DivideTool()]

    # Drive every message in the conversation. After each message the chain
    # extends; the next message uses the previous chain's last TaskRun.trace
    # as `prior_trace`, just like the chat backend does.
    full_chain: list[TaskRun] = []
    per_message_chain_lens: list[int] = []
    for idx, user_msg in enumerate(_TEN_MESSAGE_CONVO):
        prior = full_chain[-1].trace if full_chain else None
        chain = await _drive_user_turn(
            adapter,
            user_msg,
            prior_trace=prior,
            math_tools=math_tools,
            streaming=streaming,
        )
        per_message_chain_lens.append(len(chain))
        full_chain.extend(chain)

        # Sanity: the chain only ever grows. After every user message we
        # should have AT LEAST one new TaskRun, and the last TaskRun in
        # the chain should not be in a pending state — the loop only
        # exits a user turn when the model produced a final assistant
        # message.
        assert len(chain) >= 1, f"user message #{idx} produced no TaskRuns"
        assert not chain[-1].is_toolcall_pending, (
            f"user message #{idx}'s chain ends with a tool-call-pending run; "
            f"loop should only exit on a final assistant message"
        )

    # ── Coverage check: the full conversation hit BOTH patterns. ──
    pending_rounds_total = sum(1 for r in full_chain if r.is_toolcall_pending)
    plain_user_messages = sum(1 for n in per_message_chain_lens if n == 1)
    assert pending_rounds_total >= 4, (
        f"Across the full 10-message conversation we should have hit ≥ 4 "
        f"tool-call rounds; got {pending_rounds_total}. The model may have "
        f"answered most questions without using the tools."
    )
    assert plain_user_messages >= 1, (
        f"At least one user message should have been answered without a "
        f"tool call (e.g. the greeting / confirmation prompts); got "
        f"per-message chain lengths {per_message_chain_lens}."
    )

    # ── The canonical assertion: every step's per-message usage is
    # preserved, and `cumulative_usage` on each TaskRun equals the running
    # total of every prior TaskRun's `usage` plus this one's. This is the
    # chat-undercount sentinel: any inference call whose tokens get lost
    # — whether on the running aggregator or on the seeded prior trace
    # — will trip this assertion. ──
    _assert_per_message_usage_chain_consistent(full_chain)

    # ── Final-snapshot check: the LAST TaskRun's trace (which a chat UI,
    # eval, or billing dashboard would render as "the conversation
    # history") carries per-message usage on EVERY assistant message in
    # it. A failure here points unambiguously at the final-snapshot path
    # (vs. the running aggregator, which the previous assertion covers). ──
    _assert_last_trace_has_usage_on_every_assistant(full_chain[-1])

    # ── Strongest precise check: the LAST TaskRun's trace anchors each
    # TaskRun's individual `usage` at the exact assistant-message slot
    # corresponding to the inference that produced it. ──
    _assert_last_trace_anchors_each_taskrun_usage(full_chain)

    # ── Last trace's cumulative_usage equals MessageUsage.from_trace of
    # the last trace, AND equals the sum of every TaskRun.usage in the
    # chain. Both directions, explicitly. ──
    last = full_chain[-1]
    last_trace = last.trace
    assert last_trace is not None
    sum_of_last_trace = MessageUsage.from_trace(last_trace)
    sum_of_chain_usages: MessageUsage = MessageUsage()
    for r in full_chain:
        assert r.usage is not None
        sum_of_chain_usages = sum_of_chain_usages + MessageUsage(
            input_tokens=r.usage.input_tokens,
            output_tokens=r.usage.output_tokens,
            total_tokens=r.usage.total_tokens,
            cost=r.usage.cost,
            cached_tokens=r.usage.cached_tokens,
        )

    assert last.cumulative_usage is not None
    assert (
        last.cumulative_usage.input_tokens
        == sum_of_last_trace.input_tokens
        == sum_of_chain_usages.input_tokens
    ), (
        f"Three input_tokens totals must agree:\n"
        f"  last.cumulative_usage.input_tokens = {last.cumulative_usage.input_tokens}\n"
        f"  sum-of-last-trace.input_tokens     = {sum_of_last_trace.input_tokens}\n"
        f"  sum-of-chain-TaskRun.usage         = {sum_of_chain_usages.input_tokens}\n"
        f"A mismatch tells you which path lost an inference: trace lost "
        f"means per-message usage didn't make it onto a message; chain-sum "
        f"lost means a TaskRun.usage didn't reflect one of its calls."
    )
    assert (
        last.cumulative_usage.output_tokens
        == sum_of_last_trace.output_tokens
        == sum_of_chain_usages.output_tokens
    ), (
        f"output_tokens mismatch: cumulative={last.cumulative_usage.output_tokens}, "
        f"trace_sum={sum_of_last_trace.output_tokens}, "
        f"chain_sum={sum_of_chain_usages.output_tokens}"
    )
    assert (
        last.cumulative_usage.total_tokens
        == sum_of_last_trace.total_tokens
        == sum_of_chain_usages.total_tokens
    ), (
        f"total_tokens mismatch: cumulative={last.cumulative_usage.total_tokens}, "
        f"trace_sum={sum_of_last_trace.total_tokens}, "
        f"chain_sum={sum_of_chain_usages.total_tokens}"
    )
    assert (
        last.cumulative_usage.cached_tokens
        == sum_of_last_trace.cached_tokens
        == sum_of_chain_usages.cached_tokens
    ), (
        f"cached_tokens mismatch: cumulative={last.cumulative_usage.cached_tokens}, "
        f"trace_sum={sum_of_last_trace.cached_tokens}, "
        f"chain_sum={sum_of_chain_usages.cached_tokens}"
    )
    if last.cumulative_usage.cost is not None:
        assert sum_of_last_trace.cost is not None
        assert sum_of_chain_usages.cost is not None
        assert last.cumulative_usage.cost == pytest.approx(sum_of_last_trace.cost)
        assert last.cumulative_usage.cost == pytest.approx(sum_of_chain_usages.cost)

    # Sanity: the final cumulative_usage strictly exceeds the first one.
    first = full_chain[0]
    assert first.cumulative_usage is not None
    last_input = last.cumulative_usage.input_tokens
    first_input = first.cumulative_usage.input_tokens
    assert last_input is not None and first_input is not None
    assert last_input > first_input, (
        "Chain's last cumulative_usage.input_tokens is not strictly greater "
        "than the first run's — the chain's tokens stopped accumulating "
        "across user messages."
    )


@pytest.mark.paid
async def test_full_chat_session_sync(tmp_path):
    """End-to-end 10-user-message chat session via the SYNCHRONOUS
    `adapter.invoke(...)` API. Mirrors the chat backend's per-round loop:
    `return_on_tool_call=True` interrupt → server-side tool execution via
    `adapter.process_tool_calls` → resume with `input=tool_msgs,
    prior_trace=task_run.trace`. The 10-message conversation mixes plain
    user→assistant exchanges (greetings, confirmations) with multi-tool-
    round back-and-forths. Verifies per-message usage and `cumulative_usage`
    accumulate correctly across the entire chain."""
    await _run_chat_session(streaming=False, tmp_path=tmp_path)


@pytest.mark.paid
async def test_full_chat_session_streaming(tmp_path):
    """Same 10-user-message conversation as ``test_full_chat_session_sync``
    but using `adapter.invoke_ai_sdk_stream(...)` — the streaming entry
    point the production chat backend
    (kiln_server/api/.../chat/stream_orchestration.py) actually uses.
    Exhausts each stream to access `.task_run` then drives the same
    tool-execution-and-resume loop."""
    await _run_chat_session(streaming=True, tmp_path=tmp_path)
