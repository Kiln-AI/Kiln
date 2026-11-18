---
status: complete
---

# Phase 4: Model list changes (branch 2)

## Overview

Branch 1 upgraded LiteLLM to 1.105.6, which sends tool calls with reasoning on to `/v1/responses` for GPT-5.4+ and GPT-6+ on OpenAI direct. This phase changes the model list to match, on branch 2 (`claude/pensive-cannon-3jnl5q-model-list`), which merges only after the release with branch 1 is live:

- Turn tools on for the ten OpenAI-direct providers that have them off: GPT-5.4, GPT-5.5, GPT-5.6 Sol/Terra/Luna, GPT-6 Astra/Sol/Luna, GPT-6.1 Sol/Terra.
- Hide `max` on the OpenAI-direct providers of GPT-6 Astra, Sol and Luna. `/v1/chat/completions` rejects it, and LiteLLM uses Chat Completions for every call without tools or summaries. OpenRouter keeps `max`.
- Pin both with model-list tests and an offline routing test, add the branch 2 paid tests, and finish the maintainer docs.

GPT-6.1 Terra keeps `none`. The F6 check (tools at `none` on Terra) is a paid case the team runs; its level list changes only if that case fails.

## Steps

1. **Tools on** (`libs/core/kiln_ai/adapters/ml_model_list.py`). On the `ModelProviderName.openai` provider of `gpt_6_1_sol`, `gpt_6_1_terra`, `gpt_6_astra`, `gpt_6_sol`, `gpt_6_luna`, `gpt_5_6_sol`, `gpt_5_6_terra`, `gpt_5_6_luna`, `gpt_5_5` and `gpt_5_4`, delete `supports_function_calling=False` and the three-line comment above it.

2. **New level constants** (same file). Replace the `GPT_6_1_SOL_OPENAI_THINKING_LEVELS` block with one group after `GPT_6_OPENAI_THINKING_LEVELS`, under one comment that gives the reason once:

   ```python
   # OpenAI direct hides `max` on GPT-6 Astra, Sol and Luna and on GPT-6.1 Sol and Terra.
   # /v1/chat/completions rejects `max` for these models with a 400; only /v1/responses
   # accepts it. LiteLLM sends a call to Responses only when tools are attached or a
   # reasoning summary is requested, so a `max` run without either fails. Restore `max`
   # once every call to these models goes to Responses.
   GPT_6_ASTRA_OPENAI_DIRECT_THINKING_LEVELS = {"Low": "low", "Medium": "medium", "High": "high", "Extra High": "xhigh"}
   GPT_6_OPENAI_DIRECT_THINKING_LEVELS = {"Off/None": "none", "Low": "low", "Medium": "medium", "High": "high", "Extra High": "xhigh"}

   # GPT-6.1 Sol also rejects `none` and `minimal` on both endpoints.
   # https://developers.openai.com/api/docs/models/gpt-6.1-sol
   GPT_6_1_SOL_OPENAI_THINKING_LEVELS = {...unchanged values...}
   ```

   - Point `gpt_6_astra`'s OpenAI provider at `GPT_6_ASTRA_OPENAI_DIRECT_THINKING_LEVELS`, and `gpt_6_sol`'s and `gpt_6_luna`'s at `GPT_6_OPENAI_DIRECT_THINKING_LEVELS`. Their OpenRouter providers, and every other user of `GPT_6_ASTRA_OPENAI_THINKING_LEVELS` and `GPT_6_OPENAI_THINKING_LEVELS`, keep `max`.
   - Reword the comment on GPT-6.1 Terra's OpenAI provider to point at the same reason: `max` is hidden for the reason given above `GPT_6_ASTRA_OPENAI_DIRECT_THINKING_LEVELS`. Its level list (`GPT_5_4_OPENAI_THINKING_LEVELS`) stays.

3. **Model-list tests** (`libs/core/kiln_ai/adapters/test_ml_model_list.py`). No existing assertion expects tools off or `max` on these entries, so only new tests are needed (see Tests).

4. **Offline routing test** (`libs/core/kiln_ai/adapters/model_adapters/test_openai_responses_wire.py`). One parametrized case per OpenAI-direct provider that sets `openai_reasoning_summary` and per thinking level it offers. Tools attached, summaries off. Both endpoints are mocked; the test asserts that `none` goes to `/v1/chat/completions` and every other level goes to `/v1/responses`. This pins the functional spec's F3 table for the real model ids, so a LiteLLM upgrade that stops bridging one of them fails offline instead of with OpenAI's 400.

5. **Shared paid-test list** (`libs/core/kiln_ai/adapters/model_adapters/test_paid_utils.py`). Add `OPENAI_RESPONSES_TOOL_MODELS: list[ModelName]`, the ten models above, with a comment saying LiteLLM sends their tool calls to `/v1/responses` when reasoning is on, and that the Pro models are left out because they always go there (covered by `test_tools_store_false_gpt_5_4_pro`).

6. **Paid tools tests** (`libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py`).
   - `run_simple_task_with_tools` gets `thinking_level: str | None = None`, passed to `KilnAgentRunConfigProperties`.
   - `test_openai_tools_every_thinking_level_paid`: parametrized over each model in `OPENAI_RESPONSES_TOOL_MODELS` and every level its OpenAI provider offers, ids `<model>-<level>`. Runs the simplified add-tool task at that level. This includes `none`, which covers GPT-5.4's default and the F6 check on GPT-6.1 Terra.
   - `test_openai_narration_then_tool_call_paid`: each of the ten at `medium` (which goes to Responses). The prompt asks for one sentence before the tool calls, then 11 + 50 and 50 × 85 with the tools, then their sum. Asserts some assistant turn carries both text and tool calls (with a message saying the case wasn't exercised if not), that multiply and add ran, and that the output contains `4311`.
   - Both call `skip_if_missing_provider_keys(ModelProviderName.openai)`.

7. **Paid streaming tests** (`libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_streaming.py`).
   - Build `OPENAI_DIRECT_TOOL_MODELS` from `OPENAI_RESPONSES_TOOL_MODELS`, each at its OpenAI provider's default level (`default_thinking_level_for_model_provider`), and append it to `STREAMING_MODELS` and `RETURN_ON_TOOL_CALL_MODELS`.
   - OpenAI direct returns no reasoning with summaries off, so `test_invoke_openai_stream_chunks` and `test_invoke_ai_sdk_stream` assert reasoning only when the provider isn't `ModelProviderName.openai`, through one small helper with a comment giving that reason. Every other assertion stays, so the streamed tool loop and the `return_on_tool_call` resume both have to round-trip on OpenAI.

8. **Maintainer docs** (`.agents/skills/claude-maintain-models/SKILL.md`).
   - OpenAI quirks: new OpenAI-direct GPT-5.4+ and GPT-6+ models keep `supports_function_calling` at its default, because LiteLLM sends their tool calls to `/v1/responses`. Never offer `max` on an `openai` provider, with the reason, the two constants, and the test that enforces it; OpenRouter keeps `max`. Run `test_openai_tools_every_thinking_level_paid` for a new model, and report a failure at `none` instead of removing the level (it may be the default).
   - Thinking-level lookup chain, OpenAI bullet: leave out `max` on OpenAI direct, linking the quirk.
   - Existing constants table: add the two new constants, and the two `max` constants with "OpenRouter" in their "Used by" column.

9. **Docs sync.** Run the `docs-sync` skill over `origin/claude/pensive-cannon-3jnl5q...` plus this phase's working tree. The research notes under `specs/research/openai-responses-api/` describe the code at the time of the research and stay as they are.

10. **Checks.** `uv run ./checks.sh --agent-mode` and the conventions gate (`--worktree`).

## Tests

Model list (`test_ml_model_list.py`):

- `test_openai_reasoning_summary_providers_support_tools`: every OpenAI-direct provider that sets `openai_reasoning_summary` has `supports_function_calling` true. That is the ten plus the two Pro models.
- `test_openai_direct_providers_hide_max`: no `ModelProviderName.openai` provider offers `max`.
- `test_gpt_6_openai_direct_hides_only_max` (parametrized over `gpt_6_astra`, `gpt_6_sol`, `gpt_6_luna`): the OpenAI-direct levels equal the OpenRouter levels without `max`, and OpenRouter still offers `max`.

Offline wire (`test_openai_responses_wire.py`):

- `test_tool_runs_use_responses_unless_thinking_is_off` (parametrized over every OpenAI-direct summary provider and level): with tools attached, `none` calls only `/v1/chat/completions`, every other level calls only `/v1/responses`, and the run returns the mocked answer.

Paid (written here, run by the team with a real OpenAI key):

- `test_openai_tools_every_thinking_level_paid[<model>-<level>]`: a tool run succeeds on each of the ten at every level.
- `test_openai_narration_then_tool_call_paid[<model>]`: a reply with text and tool calls runs the tools.
- The ten at their default level in `STREAMING_MODELS` and `RETURN_ON_TOOL_CALL_MODELS`: streamed tool loops, AI SDK events, text-before-tools, prior-trace continuation, and the `return_on_tool_call` resume.

Paid-test commands for the team:

```
uv run python3 -m pytest --runpaid -q -n auto libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py -k "test_openai_tools_every_thinking_level_paid or test_openai_narration_then_tool_call_paid"
uv run python3 -m pytest --runpaid -q -n auto libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_streaming.py -k "gpt_5 or gpt_6"
```

The F6 check alone:

```
uv run python3 -m pytest --runpaid -q "libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py::test_openai_tools_every_thinking_level_paid[gpt_6_1_terra-none]"
```
