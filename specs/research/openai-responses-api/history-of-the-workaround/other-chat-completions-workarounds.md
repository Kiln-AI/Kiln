# Other workarounds in the model list that come from using Chat Completions

These exist alongside `supports_function_calling=False`. Each one is listed with where it lives, why it exists, its source, and what the current LiteLLM (1.102.0) does.

## 1. `max` thinking level hidden on GPT-6.1 Sol and GPT-6.1 Terra (OpenAI direct)

- `libs/core/kiln_ai/adapters/ml_model_list.py`:
  ```python
  # GPT-6.1 Sol on OpenAI direct. The model page lists `max` as well, but
  # /v1/chat/completions (which Kiln uses) rejects it with a 400; only
  # /v1/responses accepts it. `none` and `minimal` are rejected on both.
  GPT_6_1_SOL_OPENAI_THINKING_LEVELS = { "Low", "Medium", "High", "Extra High" }
  ```
  GPT-6.1 Terra's OpenAI provider uses `GPT_5_4_OPENAI_THINKING_LEVELS` with the comment "/v1/chat/completions accepts none through xhigh for this model and rejects max with a 400."
- Added in [#1830](https://github.com/Kiln-AI/Kiln/pull/1830) (2026-10-01) and [#1982](https://github.com/Kiln-AI/Kiln/pull/1982) (2026-10-28). The OpenRouter providers for both models keep `max`.
- Routing only `tools + effort` calls to Responses would **not** unlock `max`. A tool-less `max` call still goes to `/v1/chat/completions`; the fake-server run shows `gpt_6_1_sol level=max: /v1/chat/completions {"reasoning_effort": "max", ...}` ([current-state.md](./current-state.md), section F). Offering `max` needs every call for these models routed to Responses, not just tool calls.

## 2. `max` still offered on GPT-6 Astra, Sol and Luna (OpenAI direct): a live bug

- `gpt-6-astra` uses `GPT_6_ASTRA_OPENAI_THINKING_LEVELS`, and `gpt-6-sol` / `gpt-6-luna` use `GPT_6_OPENAI_THINKING_LEVELS`. Both constants include `"Max": "max"`, and both are used on the OpenAI-direct providers.
- OpenAI's Chat Completions rejects `max` for all three (probe in [#1831](https://github.com/Kiln-AI/Kiln/pull/1831), 2026-09-29, quoted in [openai-error-messages.md](./openai-error-messages.md)). #1830 states: "a user who picked "Max" for a GPT-6 model on the OpenAI provider got a failed run every time".
- #1831, which would have split these constants per provider, was **closed without merge** on 2026-10-13. Nothing in `main` replaced it, so the three providers still offer a level that fails on every tool-less run.
- Separately, GPT-5.6 Sol's `max` was rejected "deterministically on both providers" (OpenRouter too) in #1560. That model does not support `max` at all, so it is not a Chat Completions limitation.

## 3. Missing reasoning text on OpenAI-direct GPT reasoning models

- Kiln has no model-list flag for this; it shows up as failing paid tests. `test_thinking_level_reasoning_content` asserts that reasoning content is present for non-`none` levels. On `main` it has carve-outs for Anthropic and Gemini adaptive models but none for OpenAI GPT.
- Cause as recorded by Kiln PRs: "OpenAI only returns reasoning *summary* text via its Responses API (`reasoning.summary`)" ([#1562](https://github.com/Kiln-AI/Kiln/pull/1562)); "OpenAI's Chat Completions route never returns reasoning text for any OpenAI model (0 of 61 live cases across the catalog)" ([#1806](https://github.com/Kiln-AI/Kiln/pull/1806)).
- History: #1562 (test carve-out) was approved and then closed unmerged. #1560, #1755, #1806, #1830, #1894 and #1982 each shipped with these failures marked "pre-existing". #1982 records the author's view that "the provider likely hides reasoning text now to prevent distillation". That is an opinion; no source is given.
- Routing to Responses alone does not fix this. The request must also ask for a summary: #1757 commit `ca276a72`, "OpenAI's /v1/responses returns no reasoning at all unless the request asks for a summary". Kiln sends no `reasoning_summary` today, so even calls that LiteLLM already bridges (tools on gpt-5.4-pro / gpt-5.2-pro) get no reasoning text. #1757's paid runs also show summaries are intermittent even when requested: 18 of 30 passed on the branch, with a different set failing on each run.
- OpenRouter's twins also return reasoning only some of the time (#1806, #1894, #1982). That is a separate behavior, not caused by Chat Completions on OpenAI.

## 4. `temperature` / `top_p` with reasoning on

- No model-list flag exists for OpenAI. `temp_top_p_exclusive` is for Anthropic. #1806: "Kiln has no provider flag for "this model only accepts the default temperature". Kiln's default is 1.0, so the common path works, but a user who explicitly sets any other temperature on a GPT-6 model — Astra included — gets the same 400." The UI temperature field is free-form.
- Under LiteLLM 1.87.1, GPT-6 models with `temperature=0` got a 400 on OpenAI direct (#1806). Kiln's paid test was changed to always send `temperature = 1` ("GPT-6 rejects any other", `test_thinking_level_paid.py`).
- **Under LiteLLM 1.102.0 the 400 is gone and the value is silently dropped.** Measured with the fake server, `litellm.acompletion(..., drop_params=True)` as Kiln calls it:
  ```
  gpt-6-astra  effort=high   sent temp=0.0 top_p=0.5 -> /v1/chat/completions temperature=<absent> top_p=<absent> reasoning_effort=high
  gpt-6-sol    effort=none   sent temp=0.0 top_p=0.5 -> /v1/chat/completions temperature=0.0 top_p=0.5 reasoning_effort=none      (live map)
  gpt-6-sol    effort=none   sent temp=0.0 top_p=0.5 -> /v1/chat/completions temperature=<absent> top_p=<absent> reasoning_effort=none  (bundled map: model missing)
  gpt-5.5      effort=high   sent temp=0.0 top_p=0.5 -> /v1/chat/completions temperature=<absent> top_p=<absent> reasoning_effort=high
  gpt-5.5      effort=none   sent temp=0.0 top_p=0.5 -> /v1/chat/completions temperature=0.0 top_p=0.5 reasoning_effort=none
  gpt-5.4      effort=medium sent temp=0.7 top_p=1.0 -> /v1/chat/completions temperature=<absent> top_p=<absent> reasoning_effort=medium
  ```
  The bridged path behaves the same (fake run D in [current-state.md](./current-state.md)). LiteLLM decides from the model map (`effort_resolves_to_none`, `supports_none_reasoning_effort`), so the result can change with the live map and differs when the map lacks the model.
- With the default `temperature: 1.0`, LiteLLM keeps `temperature: 1.0` on both endpoints for these models. `top_p` is dropped on the bridged path.

## 5. Pro models

- **GPT-5.4 Pro and GPT-5.2 Pro have OpenAI-direct providers with tools on, and every call already goes to `/v1/responses`.** LiteLLM's model map marks both `"mode": "responses"`, in the 1.102.0 bundled map and in the live map. The 1.87.1 bundled map has both; the 1.81.16 bundled map has `gpt-5.2-pro` and lacks `gpt-5.4-pro`. The static probe shows `R` for these two at every effort, with and without tools, and the fake run routes a tool-less `gpt_5_4_pro` call to `/v1/responses`.
  - So Kiln already ships LiteLLM's chat-to-responses conversion in production, with tools enabled. Their thinking levels have no `none` (`GPT_5_4_PRO_OPENAI_THINKING_LEVELS`, `GPT_5_2_PRO_OPENAI_THINKING_LEVELS`: medium, high, xhigh).
  - Inference (same code path, not separately measured on these ids): the defects in [current-state.md](./current-state.md) apply to them today. That means the split text-plus-tool-call turn, `strict: false`, no reasoning summary, and default `store`.
  - #1103 (2026-03-11) and #1351 (2026-04-28) both record `test_tools_all_built_in_models[gpt_5_4_pro-openai]` passing.
- **GPT-6 Pro models are OpenRouter-only in Kiln.** `gpt_6_1_sol_pro`, `gpt_6_1_terra_pro`, `gpt_6_sol_pro`, `gpt_6_luna_pro` have only `openrouter` providers. [#1894](https://github.com/Kiln-AI/Kiln/pull/1894): "OpenAI direct does not serve these ids ... a live call to each id on both `/v1/chat/completions` and `/v1/responses` returns "model does not exist". On OpenAI, Pro is a request parameter, not a model id." [#1982](https://github.com/Kiln-AI/Kiln/pull/1982): "OpenRouter serves the same model with `reasoning.mode` set to `pro`." OpenAI's reasoning guide says: "If you're using a GPT-5.6 or GPT-6 model, see reasoning mode for its `pro` option." Whether the Pro reasoning mode exists on Chat Completions at all is not established here; that belongs to the OpenAI subtopic.

## 6. OpenRouter's reasoning object (a sibling workaround, not Chat Completions on OpenAI)

Every OpenRouter twin of the affected models sets `openrouter_reasoning_object=True`, with the comment "Use OpenRouter's reasoning object so reasoning is preserved when tools are sent (the bare reasoning_effort param is silently dropped on tool calls for these models)". This was introduced in #1351. It explains why "the OpenRouter route is unaffected": tools and reasoning work there, through OpenRouter's own API.

## 7. Historical: `xhigh` silently dropped by LiteLLM 1.81.16

Not a model-list workaround, but the same pattern of a level being lost without an error. LiteLLM 1.81.16 `OpenAIGPT5Config.map_openai_params` pops `reasoning_effort` when it is `"xhigh"` and the model is not `gpt-5.1-codex-max` or `gpt-5.2*`, as long as `drop_params` is on (Kiln always sets it). So from 2026-03-11 to 2026-06-18, Kiln's "Extra High" level on `gpt-5.4` / `gpt-5.5` was sent with no effort at all. #1351's "full thinking-level matrix passed end-to-end (none/low/medium/high/xhigh)" could not detect this, because the run still succeeds. This is inferred from source and was not observed on the wire.
