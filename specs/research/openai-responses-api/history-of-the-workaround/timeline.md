# Timeline: why tools are off on OpenAI-direct GPT-5.4+ / GPT-6 providers

Every step below gives the date, the Kiln PR, which OpenAI-direct providers changed, the LiteLLM version locked in `uv.lock` on `main` at that moment, and whether that LiteLLM version would already have sent a tools-plus-reasoning request to `/v1/responses` without Kiln asking.

Method: `git log -S "OpenAI rejects reasoning_effort + tools" -- libs/core/kiln_ai/adapters/ml_model_list.py` on `origin/main` (the local clone was shallow at 2026-05-15, so history was deepened with `git fetch --shallow-since=2025-12-01 origin main`), `git show <commit>:uv.lock` for the lock, the PR pages via the GitHub MCP tools, and the LiteLLM source of each locked version (1.102.0 installed in `.venv`; 1.81.16 and 1.87.1 wheels downloaded from PyPI and read, not executed).

## The LiteLLM lock on `main` over time

| Lock on `main` from | Commit / PR | LiteLLM | Pin in `libs/core/pyproject.toml` |
|---|---|---|---|
| 2026-02-27 | `20d2450a` ([#1090](https://github.com/Kiln-AI/Kiln/pull/1090)) | 1.81.16 | `litellm>=1.81.16` then `>=1.81.16,<1.82.7` (2026-03-24, commit `4fb7635e`, "Explicitly block compromised versions of LiteLLM") |
| 2026-06-18 | `9ab00d73` ([#1480](https://github.com/Kiln-AI/Kiln/pull/1480)) | 1.87.1 | `litellm>=1.87.0,<1.88` |
| 2026-09-30 | `a597a25d` ([#1829](https://github.com/Kiln-AI/Kiln/pull/1829)) | 1.102.0 | `litellm>=1.102.0,<1.103` |

Neither LiteLLM bump was made for OpenAI. #1480 bumped for Anthropic Opus 4.7/4.8 thinking ("The pinned `litellm 1.81.16` sent the legacy `thinking:{type:enabled, budget_tokens}` payload ... Bumped litellm to **1.87.1**"). #1829 bumped for Claude 5.x native structured output ("litellm 1.87 cannot use native JSON-schema output for Claude 5.x models"). Neither PR mentions OpenAI routing. Both bumps changed how OpenAI tool calls are routed as a side effect.

Released desktop builds (tag → locked LiteLLM, from `git show <tag>:uv.lock`): v0.27.x – v1.0.2 (to 2026-05-11) ship 1.81.16; v1.0.3 (2026-06-23) through v1.2.0 (2026-09-28, the latest tag on `origin`) ship 1.87.1. **No released build ships LiteLLM 1.102.0 yet.** This matters because the remote model list replaces the built-in list on every client (`built_in_models[:] = models.model_list` in `libs/core/kiln_ai/adapters/remote_config.py`).

## What each LiteLLM version does with tools + `reasoning_effort` on `openai/<gpt id>`

Source: `responses_api_bridge_check` in `litellm/main.py`, plus `OpenAIGPT5Config` in `litellm/llms/openai/chat/gpt_5_transformation.py`.

- **1.81.16** — no automatic rule. The function only routes to Responses when the model id has a `responses/` prefix or the model map entry says `mode: responses`. Every Kiln tools-plus-reasoning call for gpt-5.4+ went to `/v1/chat/completions`.
- **1.87.1** — automatic rule added:
  ```python
  and OpenAIGPT5Config.is_model_gpt_5_model(model)
  and not OpenAIGPT5Config.is_model_gpt_5_search_model(model)
  and reasoning_effort is not None
  and (
      reasoning_summary is not None
      or (OpenAIGPT5Config.is_model_gpt_5_4_plus_model(model) and tools)
  )
  ```
  `is_model_gpt_5_model` is `"gpt-5" in model and not _normalized.startswith("gpt-5-chat")`, and `is_model_gpt_5_4_plus_model` requires the name to start with `gpt-5.` and have minor version >= 4. So 1.87.1 bridged **gpt-5.4, gpt-5.5, gpt-5.6-\*** whenever tools were present and `reasoning_effort` was set to anything, **including `"none"`**. It did **not** bridge any `gpt-6*` name.
- **1.102.0** — the rule was widened and tightened:
  ```python
  OpenAIGPT5Config.is_model_gpt_5_4_plus_model(model)
  and has_function_tool
  and reasoning_active            # effort != "none"
  and (reasoning_effort is not None or on_constraint_enforcing_endpoint)
  ```
  `is_gpt_reasoning_series_name` now matches `"gpt-5"` or `"gpt-6"`, and `is_model_gpt_5_4_plus_model` returns True for any name starting with `gpt-6`. So 1.102.0 bridges **all ten** affected Kiln model ids when tools are present and the effort is not `"none"`. An explicit `"none"` stays on Chat Completions. The source comment quotes OpenAI: "Chat Completions rejects function tools whenever reasoning is on ("Function tools with reasoning_effort are not supported ... use /v1/responses or set reasoning_effort to 'none'"), so only an explicit ``"none"`` keeps the request chat-servable."

Kiln always passes `reasoning_effort` as a top-level LiteLLM argument when the provider has thinking levels (`build_extra_body` in `libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py`), so the "explicit effort" branch is the one that applies to Kiln.

## Step by step

### 2026-03-11 — GPT-5.4 added with tools on ([#1103](https://github.com/Kiln-AI/Kiln/pull/1103))
- Added `gpt-5.4` and `gpt-5.4-pro` on OpenAI direct and OpenRouter. `gpt-5.4` used `GPT_5_4_OPENAI_THINKING_LEVELS`, `default_thinking_level="none"`, and the default `supports_function_calling=True`.
- Lock: LiteLLM 1.81.16 (no automatic routing).
- Paid results in the PR: `✅ test_tools_all_built_in_models[gpt_5_4-openai]` and `✅ test_tools_all_built_in_models[gpt_5_4_pro-openai]`.
- The tools test sets no thinking level (`run_simple_task_with_tools` in `test_litellm_adapter_tools.py`), so Kiln sent the provider default, `reasoning_effort: "none"`.
- Outside Kiln, the error was already being reported for non-`none` efforts on gpt-5.4 that week: open-webui [#22343](https://github.com/open-webui/open-webui/issues/22343) (2026-03-07), LiteLLM [#23156](https://github.com/BerriAI/litellm/issues/23156) (2026-03-09, on LiteLLM 1.82.0), pipecat [#4043](https://github.com/pipecat-ai/pipecat/issues/4043) (2026-03-16).

### 2026-04-30 — workaround introduced for GPT-5.5 and GPT-5.4 ([#1351](https://github.com/Kiln-AI/Kiln/pull/1351), commit `61129229`)
- GPT-5.5 added with `supports_function_calling=False` from its first commit on the branch; GPT-5.4 got the same flag in a follow-up commit on 2026-04-28.
- Lock: LiteLLM 1.81.16 (no automatic routing). **The workaround was needed at this point.**
- Why, from the commit message: "OpenAI rejects reasoning_effort + tools on /v1/chat/completions for GPT-5.4+ with a 400. Even default_thinking_level="none" sends reasoning_effort: "none", which trips the same check. Set supports_function_calling=False so the model list reflects what actually works at runtime, per review feedback. Once the adapter routes these models to /v1/responses (or strips reasoning_effort when tools are present), this can be re-enabled."
- The flag was suggested by review bots: gemini-code-assist ("`supports_function_calling` should be set to `False` for this provider until the underlying adapter issue (routing to `/v1/responses` or stripping reasoning parameters) is resolved") and CodeRabbit. The human reviewer's thread says: "disabling tool calls on GPT 5.4 due to this issue until we adopt response api" ([review comment](https://github.com/Kiln-AI/Kiln/pull/1351#discussion_r3156873441)).
- Scope test recorded in the PR body: "`gpt-5` ✅, `gpt-5.1` ✅, `gpt-5.2` ✅, `gpt-5.4` ❌ (now disabled on direct), `gpt-5.4-pro` ✅, ... `gpt-5.5` ❌ (now disabled on direct), `gpt-5.5-openrouter` ✅". The PR calls it "the OpenAI policy change".
- **The PR does not quote OpenAI's error text.** It only says "a 400".
- Notable: the same tools test, at the same default `"none"`, passed for gpt-5.4 on 2026-03-11 and failed on 2026-04-28 on the same LiteLLM lock. Inference (not verified): OpenAI rejected `"none"` plus tools on gpt-5.4 for at least part of this period and accepted it before. LiteLLM 1.87.1's rule, which bridges even `"none"`, matches that. OpenAI's later error text and current docs accept `"none"` (see [openai-error-messages.md](./openai-error-messages.md)).
- The OpenRouter provider kept tools on, and got `openrouter_reasoning_object=True` because "when tools are sent alongside the bare reasoning_effort param, OpenRouter silently drops reasoning".

### 2026-06-18 — LiteLLM 1.87.1 lands ([#1480](https://github.com/Kiln-AI/Kiln/pull/1480))
- From here on, LiteLLM routes gpt-5.4 / gpt-5.5 / gpt-5.6-* tools-plus-reasoning calls to `/v1/responses` by itself. For these names the flag no longer prevents a 400. It only prevents users from reaching the bridged path. Closed PR #1757 says the same: "litellm 1.87.1 already sends the gpt-5.x names to `/v1/responses` when the request has tools and a reasoning effort, so those five flags were stale since #1480." This document confirms that from the 1.87.1 source (above).
- Nobody noticed at the time. #1480 does not mention OpenAI.

### 2026-07-10 → 2026-07-21 — reasoning summaries ([#1562](https://github.com/Kiln-AI/Kiln/pull/1562), closed, not merged)
- A test-only PR to relax `test_thinking_level_reasoning_content` for OpenAI GPT-5.x. Root cause as stated: "OpenAI only returns reasoning *summary* text via its Responses API (`reasoning.summary`). Kiln invokes every model through `litellm.acompletion` (chat/completions), which returns no reasoning field for these models, so `message.reasoning_content` is always `None`." It also says: "The durable fix — routing OpenAI GPT-5.x through the Responses API to actually surface reasoning summaries (and re-enable function calling) — is a larger effort tracked separately."
- leonardmq approved on 2026-07-13. It was closed without merge on 2026-07-21. No closing comment explains why.

### 2026-07-14 — GPT-5.6 Sol, Terra, Luna added with the flag ([#1560](https://github.com/Kiln-AI/Kiln/pull/1560), commit `3fa1369c`)
- Lock: LiteLLM 1.87.1. **These names were already bridged by LiteLLM on the day they shipped**, so the flag was stale from the start. The PR copied the setting: "`supports_function_calling=False` on the OpenAI provider (pending `/v1/responses` routing, matching the existing GPT-5.4+ note)".
- The PR records the `max` rejection verbatim (see [openai-error-messages.md](./openai-error-messages.md)) and the missing reasoning content: "OpenAI's chat/completions route (which Kiln uses for these models) does not surface reasoning summaries".

### 2026-09-08 — GPT-6 Astra added with the flag ([#1755](https://github.com/Kiln-AI/Kiln/pull/1755), commit `8147fe4e`)
- Lock: LiteLLM 1.87.1. `gpt-6-astra` does **not** match 1.87.1's `"gpt-5" in model` check, so LiteLLM did not bridge it. **The flag was needed for Astra under 1.87.1.**
- PR text: "`supports_function_calling=False` on the openai-direct route (reasoning-effort + tools are rejected on `/v1/chat/completions` for GPT-5.4+)".
- Its "pre-existing failure" on `test_thinking_level_reasoning_content` was later corrected by #1806: "#1755 (GPT-6 Astra) attributed its OpenAI-route failure to reasoning not being surfaced. The test already sent `temperature=0` when that PR ran, so the actual cause on that route was the 400."

### 2026-09-08 → 2026-09-23 — first routing attempt ([#1757](https://github.com/Kiln-AI/Kiln/pull/1757), closed, not merged)
- Branch `mike/openai-responses-routing`. It added an `openai_responses_api` provider flag that made the adapter use `openai/responses/<model_id>`, re-enabled tools on the six then-affected providers, requested `reasoning_summary="auto"`, merged split choices, and sent `strict: true` on `json_schema`.
- It recorded paid evidence of three defects on the bridged path (LiteLLM 1.87.1): a turn with text and a tool call is split into two choices so Kiln drops the call ("reproduced the split-choice defect 18 of 18 times on the six models before the merge fix"); `text.format.strict` is sent as false; no reasoning text unless a summary is requested. It also states "This PR does not set `store`."
- Closed on 2026-09-23 with no closing comment. The research plan treats it as a list of leads, not a source of truth. Its LiteLLM-version claims are verified above.

### 2026-09-23 — GPT-6 Sol and Luna added with the flag ([#1806](https://github.com/Kiln-AI/Kiln/pull/1806), commit `fbb28937`)
- Lock: LiteLLM 1.87.1, which does not bridge `gpt-6-*`. **Flag needed under 1.87.1.**
- Records the `temperature` 400: "at `temperature=0` every GPT-6 request was rejected with a 400 before reaching the model", and that Chat Completions "never returns reasoning text for any OpenAI model (0 of 61 live cases across the catalog)".

### 2026-09-30 — LiteLLM 1.102.0 lands ([#1829](https://github.com/Kiln-AI/Kiln/pull/1829))
- From here on, LiteLLM bridges every affected id, including `gpt-6-*`, when tools are present and the effort is not `"none"`. On `main` the flag is now stale for all ten providers. This was not mentioned in the PR.

### 2026-10-01 — GPT-6.1 Sol added with the flag and `max` hidden ([#1830](https://github.com/Kiln-AI/Kiln/pull/1830), commit `1aed843a`)
- Lock: LiteLLM 1.102.0 (bridged from day one).
- PR text: "The entry copies the GPT-6 Sol configuration, including `supports_function_calling=False` on OpenAI, because the OpenAI model page says chat completions is available without tool calling and Kiln does not use the responses endpoint yet."
- Adds `GPT_6_1_SOL_OPENAI_THINKING_LEVELS` without `max`: "`/v1/chat/completions`, which Kiln uses through LiteLLM, rejects `max` with a 400 ... while `/v1/responses` accepts it."

### 2026-09-29 → 2026-10-13 — drop `max` on GPT-6 OpenAI ([#1831](https://github.com/Kiln-AI/Kiln/pull/1831), draft, closed, not merged)
- Found that GPT-6 Astra, Sol and Luna on OpenAI direct offer `max`, which Chat Completions rejects. It includes a dated direct API probe (2026-09-29). Closed without merge and without a comment. **`main` still offers `max` for those three providers.**

### 2026-10-28 — GPT-6.1 Terra added with the flag and `max` hidden ([#1982](https://github.com/Kiln-AI/Kiln/pull/1982), commit `8c47c94e`)
- Lock: LiteLLM 1.102.0. Copies the flag: "`supports_function_calling=False` on OpenAI direct (Kiln still calls OpenAI through `/v1/chat/completions`)". Uses `GPT_5_4_OPENAI_THINKING_LEVELS` because "`/v1/chat/completions` returned an answer for `none`, `low`, `medium`, `high` and `xhigh`, and a 400 naming exactly those five values for `max`".

## Per-provider summary

| Provider (OpenAI direct) | Flag set by | Date | Lock then | Would that lock bridge tools + effort≠none? | Stale on `main` since |
|---|---|---|---|---|---|
| `gpt-5.4` | #1351 | 2026-04-30 | 1.81.16 | No | 2026-06-18 (1.87.1) |
| `gpt-5.5` | #1351 | 2026-04-30 | 1.81.16 | No | 2026-06-18 (1.87.1) |
| `gpt-5.6-sol` | #1560 | 2026-07-14 | 1.87.1 | Yes | the day it was added |
| `gpt-5.6-terra` | #1560 | 2026-07-14 | 1.87.1 | Yes | the day it was added |
| `gpt-5.6-luna` | #1560 | 2026-07-14 | 1.87.1 | Yes | the day it was added |
| `gpt-6-astra` | #1755 | 2026-09-08 | 1.87.1 | No (name not matched) | 2026-09-30 (1.102.0) |
| `gpt-6-sol` | #1806 | 2026-09-23 | 1.87.1 | No (name not matched) | 2026-09-30 (1.102.0) |
| `gpt-6-luna` | #1806 | 2026-09-23 | 1.87.1 | No (name not matched) | 2026-09-30 (1.102.0) |
| `gpt-6.1-sol` | #1830 | 2026-10-01 | 1.102.0 | Yes | the day it was added |
| `gpt-6.1-terra` | #1982 | 2026-10-28 | 1.102.0 | Yes | the day it was added |

"Stale" here means only "LiteLLM would route the call to `/v1/responses` instead of letting OpenAI return a 400". It does **not** mean the bridged path works correctly for Kiln. See [current-state.md](./current-state.md).

Not affected: `gpt-5.4-pro` and `gpt-5.2-pro` on OpenAI direct keep `supports_function_calling=True`. LiteLLM's model map marks them `mode: responses`, so every call to them already goes through the bridge (see [other-chat-completions-workarounds.md](./other-chat-completions-workarounds.md)). `gpt-5.4-mini` / `gpt-5.4-nano` on OpenAI direct have no thinking levels in Kiln, so Kiln never sends `reasoning_effort` for them.
