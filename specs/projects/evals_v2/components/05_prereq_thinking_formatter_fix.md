---
status: complete
approved: true
alignment_refs: []
opens: []
summary: SingleTurnR1ThinkingFormatter fix — opt-in forward_thinking_instructions param for reasoning models.
---

# Prereq #2: SingleTurnR1ThinkingFormatter Drops thinking_instructions

**Source(s):** `libs/core/kiln_ai/adapters/chat/chat_formatter.py`, `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`
**Author:** sub-agent dispatched 2026-05-25 for thinking-formatter fix design
**Status:** complete (design locked; implementation follows as a standalone Kiln core commit)

## TL;DR

- **Bug:** `SingleTurnR1ThinkingFormatter` silently drops `thinking_instructions`. Any Kiln task with a `thinking_instruction` (including all GEval/llm_judge evals) loses that content when the judge model is reasoning-capable (o3, DeepSeek-R1, Claude reasoning, etc.).
- **Fix:** Add an optional `forward_thinking_instructions: bool = False` parameter to `SingleTurnR1ThinkingFormatter.__init__`. When `True`, thinking instructions are appended to the user message body. Default `False` preserves current (broken) V1 behavior per A0.1.
- **V1 behavior unchanged.** Existing callers pass no new argument and get the legacy default. V1 EvalConfigs are never affected.
- **V2 uses the fix.** V2 llm_judge (Phase 1) passes `forward_thinking_instructions=True` so reasoning-model judges receive eval_steps.
- **Standalone commit.** Shipped as a Kiln core change before V2 llm_judge lands. Not mixed into evals commit work.

## Problem Statement

`SingleTurnR1ThinkingFormatter` at `chat_formatter.py:253-271` produces messages identical to `SingleTurnFormatter`:

```python
# chat_formatter.py:254-262
class SingleTurnR1ThinkingFormatter(ChatFormatter):
    def next_turn(self, previous_output: str | None = None) -> Optional[ChatTurn]:
        if self._state == "start":
            msgs = [
                BasicChatMessage("system", self.system_message),
                BasicChatMessage("user", format_user_message(self.user_input)),
            ]
            self._state = "awaiting_final"
            self._messages.extend(msgs)
            return ChatTurn(messages=msgs, final_call=True)
```

`self.thinking_instructions` is set on the base class (`chat_formatter.py:96`) but never read in `next_turn()`.

Meanwhile, `get_chat_formatter` at `chat_formatter.py:371-372` does not even pass `thinking_instructions` to the constructor:

```python
# chat_formatter.py:371-372
case ChatStrategy.single_turn_r1_thinking:
    return SingleTurnR1ThinkingFormatter(system_message, user_input)
```

Despite `build_chat_formatter` at `base_adapter.py:610-614` providing `thinking_instructions=cot_prompt` to `get_chat_formatter`, it is silently discarded.

**Impact:** For GEval/llm_judge, `thinking_instructions` contains the eval_steps (e.g., "First, think step by step about the model's performance following these evaluation steps: 1) Does the output contain bias?..."). Reasoning-model judges never see these criteria. The model uses its native reasoning but has no guidance on what to evaluate.

## Decision: Approach

**Option B: add `forward_thinking_instructions` parameter to the existing class.** Default `False`.

Rationale over Option A (new `SingleTurnR1ThinkingFormatterV2` class + new `ChatStrategy` enum value):

- Option B requires no new class, no new enum value, no new branch in `get_chat_formatter`. One parameter addition, one conditional in `next_turn()`, and one wiring change in the caller.
- Option A would require adding `ChatStrategy.single_turn_r1_thinking_v2` to the enum (which is serialized in tuned model configs), updating `get_chat_formatter`, and adding a new class that is nearly identical to the original. More surface area for the same fix.
- Steve's guidance permits either. Option B is cleaner for one behavioral toggle.

## Implementation

### 1. `SingleTurnR1ThinkingFormatter` changes (`chat_formatter.py`)

Add `forward_thinking_instructions: bool = False` to `__init__`. When `True` and `self.thinking_instructions` is not None, append thinking instructions to the user message body, matching `TwoMessageCotFormatter` behavior:

```python
def next_turn(self, previous_output: str | None = None) -> Optional[ChatTurn]:
    if self._state == "start":
        formatted = format_user_message(self.user_input)
        if self.forward_thinking_instructions and self.thinking_instructions:
            if "<conversation_history>" in formatted:
                user_content = f"{formatted}\n\n{self.thinking_instructions}"
            else:
                user_content = f"The input is:\n<user_input>\n{formatted}\n</user_input>\n\n{self.thinking_instructions}"
        else:
            user_content = formatted
        msgs = [
            BasicChatMessage("system", self.system_message),
            BasicChatMessage("user", user_content),
        ]
        ...
```

### 2. `get_chat_formatter` changes (`chat_formatter.py:371-372`)

Pass `thinking_instructions` through to the constructor (currently dropped):

```python
case ChatStrategy.single_turn_r1_thinking:
    return SingleTurnR1ThinkingFormatter(
        system_message, user_input, thinking_instructions
    )
```

### 3. Caller opt-in

The `forward_thinking_instructions` flag propagates through `get_chat_formatter`. Two options for how callers opt in:

- **Preferred:** Add `forward_thinking_instructions: bool = False` as a parameter to `get_chat_formatter` and `build_chat_formatter`. V2 llm_judge adapter passes `True` when constructing its adapter. V1 `GEval` passes nothing (gets `False`).
- **Alternative:** V2 llm_judge constructs the formatter directly instead of going through `build_chat_formatter`. Less clean but avoids touching the shared interface.

The preferred path keeps the formatter factory as the single construction point.

## Where Thinking Instructions Land in the Message

**Appended to the user message body**, using the same `<conversation_history>` detection and `<user_input>` wrapping logic as `TwoMessageCotFormatter` (`chat_formatter.py:218-223`).

Why this placement:
- **Parity with non-reasoning path.** `TwoMessageCotFormatter` puts thinking instructions in the user message at `chat_formatter.py:220-223`. Reasoning and non-reasoning models both see the instructions in the same position (user message), just via different formatters.
- **Not the system message.** Thinking instructions are task-specific evaluation criteria, not persona/role instructions. Mixing them into the system message would change the system prompt contract.
- **Not a separate user message.** A second user message would create an unusual message structure (system, user, user) that some providers may not handle well. Single user message is simpler.

## V1 / V2 Routing

| Caller | Behavior |
|---|---|
| V1 `GEval` / `llm_as_judge` EvalConfigs | `forward_thinking_instructions=False` (default). Thinking instructions dropped for reasoning models. Existing broken behavior preserved per A0.1. |
| V2 `llm_judge` EvalConfigs (Phase 1) | `forward_thinking_instructions=True`. Reasoning models receive eval_steps in the user message. |
| Non-eval Kiln tasks | Default `False`. Callers can opt in if they set `thinking_instruction` on their Task and want reasoning models to see it. |

## Deprecation

Mark the `forward_thinking_instructions=False` default as deprecated behavior:

- Add a Python `warnings.warn("...", DeprecationWarning)` in `SingleTurnR1ThinkingFormatter.next_turn()` when `self.thinking_instructions` is not None and `self.forward_thinking_instructions` is False. This fires only when instructions are actively being dropped -- not when there are no instructions to forward.
- Add a docstring note on the parameter: "Default False preserves legacy behavior where thinking_instructions are silently dropped. New callers should pass True."
- No timeline for removing the default. It flips to `True` when V1 eval compat is no longer a constraint.

## Testing

1. **Unit test: V2 path (forward=True).** Construct `SingleTurnR1ThinkingFormatter` with `forward_thinking_instructions=True` and `thinking_instructions="eval criteria here"`. Call `next_turn()`. Assert the user message content contains `"eval criteria here"`.
2. **Unit test: V1 path (forward=False, default).** Same setup but default `forward_thinking_instructions`. Assert user message does NOT contain the thinking instructions (legacy behavior preserved).
3. **Unit test: conversation_history wrapping.** Pass user_input containing `<conversation_history>`. Verify no `<user_input>` tag wrapping when forward=True. Verify `<user_input>` wrapping when input does not contain `<conversation_history>`.
4. **Unit test: no thinking_instructions.** Pass `thinking_instructions=None` with `forward_thinking_instructions=True`. Verify no crash, user message is just the formatted input.
5. **Integration test via `build_chat_formatter`.** Construct a `BaseAdapter` subclass with a reasoning-capable provider, a task with `thinking_instruction` set, and `forward_thinking_instructions=True` threaded through. Verify the final message list includes the thinking instructions in the user message. Mock the API call, inspect the messages payload.
6. **Deprecation warning test.** Verify `DeprecationWarning` fires when `thinking_instructions` is set but `forward_thinking_instructions` is False.

Model-specific fixtures (OpenAI o3, Anthropic reasoning, DeepSeek-R1) are not needed at this layer -- the formatter is model-agnostic. The model-specific behavior (native `reasoning_content` extraction) is handled downstream in `litellm_adapter.py` and already has its own tests.

## Opens

Resolved: leave open-ended -- no specific version target for flipping the default to `True`. The flip-to-default decision is deferred to a future deprecation cycle tied to V1 eval compat sunsetting.

## Sources

- `libs/core/kiln_ai/adapters/chat/chat_formatter.py` -- `SingleTurnR1ThinkingFormatter` (lines 253-271), `TwoMessageCotFormatter` (lines 199-250), `get_chat_formatter` (lines 354-374), base class `ChatFormatter.__init__` (lines 87-99)
- `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py` -- `build_chat_formatter` (lines 570-624), reasoning_capable branch (lines 606-615)
- `research_judge_prompts/kiln_v1.md` -- Open #2 documenting the bug (line 551)
- `research_judge_prompts/_kiln_task_infrastructure_compat.md` -- formatter taxonomy and compatibility analysis (section B)
- `reference/ALIGNMENT.md` -- A0.1 backwards compatibility principle
- `PLAN.md` -- Phase 0 Prerequisite #2 (line 246)
