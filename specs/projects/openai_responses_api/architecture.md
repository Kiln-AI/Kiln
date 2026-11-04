---
status: complete
---

# Architecture: OpenAI Responses API for newer OpenAI models

Implements the [functional spec](./functional_spec.md). Kiln keeps calling `litellm.acompletion` with chat-shaped messages. LiteLLM's chat-to-responses conversion layer sends the affected calls to `/v1/responses`. Kiln changes only what it sends and how it reads replies back.

Single document. The project is small enough that component docs aren't needed.

## 1. Findings that shape the design

These come from running the real libraries on 2026-11-03: the Kiln repo in a scratch worktree, plus local fake OpenAI servers. No live OpenAI calls were made.

1. **LiteLLM 1.106.0 and later break every tool call in Kiln.** From 1.106.0, `litellm.completion()` imports its proxy MCP handler whenever `tools` is passed, for any provider. That handler imports `mcp.types.CacheableResult`, which exists only in `mcp>=2.2.0`. LiteLLM declares that `mcp` only in its optional `proxy` and `mcp` extras. Kiln locks `mcp` 1.30.0, so on 1.106.x every tool call raises `ImportError`. The adapter unit tests mock LiteLLM, so they don't catch this. I checked the wheels: 1.105.x does not import it, and 1.106.0 through 1.106.6 all do.
2. **The repo's 7-day PyPI cooldown** (`exclude-newer = "7 days"` in the root and member `pyproject.toml` files) also limits the choice. As of 2026-11-03, the newest 1.105.x allowed is **1.105.6** (published 2026-10-27).
3. **1.105.6 has the fix this project depends on.** A reply with text and a tool call comes back as one choice with both. `store` is forwarded on both endpoints. `reasoning_summary` routes the call to `/v1/responses` and becomes `reasoning.summary`.
4. **1.105.6 lacks one 1.106.0 fix: invented reasoning ids.** LiteLLM makes up an `rs_<python id>` when a replayed reasoning item has no id. Kiln never replays an id-less item: every reasoning item comes from OpenAI with an id, and Kiln's trace stores none. So this doesn't affect Kiln.
5. **Non-streamed replies lose reasoning items.** LiteLLM keeps only the last of several consecutive reasoning items, so a reply with items `rs_1` (two summary parts) and `rs_2` (one part) comes back with only `rs_2`'s text. The raw output is not exposed anywhere (`_hidden_params` and `provider_specific_fields` are empty). GPT-5.6 and later often split reasoning into several items.
6. **Streamed replies carry everything.** The terminal chunk carries every reasoning item (`id`, `encrypted_content`, all summary parts), but `litellm.stream_chunk_builder` drops them. Summary deltas arrive on choice index = `summary_index`, with no separator between parts. `stream_chunk_builder` still merges them into one choice. The AI SDK converter iterates every choice, so no text is lost on the live stream.
7. **Attaching the items fixes replay.** If the terminal `reasoning_items` are set on the rebuilt message, LiteLLM replays both items, with id and `encrypted_content`, on the next tool round under `store: false`. (Observed.)
8. **The unverified-org 400** arrives as `litellm.BadRequestError` carrying OpenAI's text, whether streamed or not.
9. **Unit tests pass on 1.105.6.** 10,235 tests pass across `libs/core`, `libs/server` and `app/desktop`. The only 5 errors are a missing `tkinter` in the sandbox, which `main` also has.

**This changes F1:** the target is the newest LiteLLM **1.105.x** that passes the cooldown (1.105.6 today), not 1.106.x. See §8.

## 2. Branch layout

| Branch | Contents | Merge |
|---|---|---|
| Branch 1 | §3.1–§3.10 | Before the release |
| Branch 2 (built on branch 1) | §4 | After the release is live, then push `remote_config` |

## 3. Branch 1

### 3.1 LiteLLM version (`libs/core/pyproject.toml`, `uv.lock`)

- Requirement: `"litellm>=1.105.6,<1.106",`. Directly above it, add a short comment: 1.106.0+ imports `mcp>=2.2` on every tool call (an optional LiteLLM extra), and Kiln is on `mcp` 1.x; raise the cap only together with an `mcp` 2.x upgrade.
- Lock with `uv lock --upgrade-package "litellm==1.105.6"`. If a newer 1.105.x has passed the cooldown by implementation time, use that instead. The lock also moves `boto3`/`botocore` (1.43.99 to 1.43.120) and `certifi`, and adds `h2`, `hpack` and `hyperframe`. `pyyaml` goes to 6.0.3, and `tiktoken` gains a 0.14.0 entry. Don't edit `uv.lock` by hand.

### 3.2 Provider field (`libs/core/kiln_ai/adapters/ml_model_list.py`)

- `KilnModelProvider` gets `openai_reasoning_summary: str | None = None`, documented in the class docstring next to `anthropic_summarized_thinking`. The docstring says: the summary mode to request from OpenAI (`reasoning.summary`), passed as-is; only sent when the user turned reasoning summaries on.
- Set `openai_reasoning_summary="auto"` on the OpenAI-direct providers of `gpt_6_1_sol`, `gpt_6_1_terra`, `gpt_6_astra`, `gpt_6_sol`, `gpt_6_luna`, `gpt_5_6_sol`, `gpt_5_6_terra`, `gpt_5_6_luna`, `gpt_5_5`, `gpt_5_4`, `gpt_5_4_pro` and `gpt_5_2_pro`. Nowhere else.
- Old clients ignore the unknown key (`test_deserialize_config_provider_with_extra_fields` already covers this).

### 3.3 Setting (`libs/core/kiln_ai/utils/config.py`)

- New property `"open_ai_reasoning_summaries": ConfigProperty(bool, default=False)`. It is file-backed and not sensitive.

### 3.4 Passing the setting to the adapter

`libs/core` code may not add new `Config.shared()` reads (conventions rule D11, gate check `core-config-shared`). `lite_llm_core_config_for_provider` already reads the OpenAI key there, so the setting is read in the same place:

- `LiteLlmCoreConfig` (`adapters/provider_tools.py`) gets `openai_reasoning_summaries: bool = False`. In the `ModelProviderName.openai` case, set it from `Config.shared().open_ai_reasoning_summaries`. This is the one new `Config.shared()` read. It FAILs the gate as an H24 case ("waits on provider config injection", the same as every case in that function). Don't allowlist it; report it in the PR.
- `LiteLlmConfig` (`model_adapters/litellm_config.py`) gets `openai_reasoning_summaries: bool = False`.
- `litellm_core_provider_config` (`adapters/adapter_registry.py`) copies the value into the `LiteLlmConfig` it builds.
- Embeddings, extractors and rerankers ignore the new field.

### 3.5 Request building (`LiteLlmAdapter.build_extra_body`)

Add two branches, each with a one-line comment saying why:

```python
if provider.name == ModelProviderName.openai:
    # Responses stores requests for 30 days by default; Kiln opts out on both endpoints.
    extra_body["store"] = False
if provider.openai_reasoning_summary is not None and self.config.openai_reasoning_summaries:
    extra_body["reasoning_summary"] = provider.openai_reasoning_summary
```

- `extra_body` is merged into the top-level kwargs (`**extra_body`). LiteLLM forwards `store` on both endpoints, and turns `reasoning_summary` into `reasoning.summary` while routing the call to `/v1/responses`.
- Don't send `include`. OpenAI returns `encrypted_content` by default when `store` is false. Also, LiteLLM forwards `include` unchanged to `/v1/chat/completions` when a call isn't routed to Responses.
- `provider.name == openai` also covers OpenAI fine-tunes (`finetune_provider_model` names them `openai`). They stay on Chat Completions, where `store: false` is valid. OpenAI-compatible custom providers have a different name, so they're excluded.

### 3.6 Non-streamed calls with summaries stream internally (`LiteLlmAdapter.acompletion_checking_response`)

Finding 5 means non-streamed calls can't return the full summary. When the kwargs contain `reasoning_summary`, this method runs the call through `StreamingCompletion` (§3.7) and validates `stream.response` exactly as it validates the non-streamed response today. Without `reasoning_summary`, it calls `litellm.acompletion` as now.

- Usage and cost come from the built response's `usage`. `usage_from_response` already falls back to `usage.cost`. (Observed: cost present on the built response.)
- Unit tests that mock `acompletion_checking_response` are unaffected.
- This change has an exit (§8 decision 2). If it doesn't stay clean, stop and propose punting before going further.

### 3.7 Streaming fixes (`adapters/litellm_utils/litellm_streaming.py`, `StreamingCompletion.__aiter__`)

For each chunk, before appending and yielding it:

1. **Collect reasoning items.** If any choice's `delta` has `reasoning_items`, keep that list. The last one seen wins; it arrives on the terminal chunk.
2. **Normalize reasoning-only deltas.**
   - For a choice whose `delta.reasoning_content` is set, and which has no `content` and no `tool_calls`, remember its original `index` as the summary part number, then set `choice.index = 0`.
   - If the part number differs from the previous reasoning delta's, prefix `"\n\n"` to `delta.reasoning_content`.
   - This keeps `invoke_openai_stream` consumers on one choice and separates parts on the live stream. It's best effort: a new reasoning item that restarts at part 0 right after a one-part item isn't detected. The saved text comes from step 3.

After `stream_chunk_builder`:

3. **Rebuild the final message from the items.** If reasoning items were collected:
   - set `message.reasoning_items` on `response.choices[0].message`;
   - if any summary part has text, set `message.reasoning_content` to all parts of all items, in order, each stripped, joined with `"\n\n"`.

   Downstream code (`_extract_reasoning_to_intermediate_outputs`, `litellm_message_to_trace_message`) then reads the full text with no further changes.

Step 3 also restores reasoning replay between tool rounds on the streaming path (finding 7). It's needed so §3.6 doesn't regress replay for non-streamed calls with summaries on. This overlaps one item of the separate "keep reasoning across turns" project. Update its handoff prompt to say that within-run streaming replay is fixed here. Saving reasoning across runs stays with that project.

Put the helpers as private module functions in `litellm_streaming.py`: `_reasoning_items_from_chunk`, `_normalize_reasoning_delta`, `_apply_reasoning_items`. No module-level mutable state; the part-number tracking lives on the `StreamingCompletion` instance.

### 3.8 Unverified-org error (`libs/core/kiln_ai/adapters/errors.py`)

- Add a constant `REASONING_SUMMARY_VERIFICATION_ERROR_MESSAGE = "Your OpenAI organization must be verified to show reasoning summaries. Verify it in your OpenAI organization settings (https://platform.openai.com/settings/organization/general), or reconnect OpenAI in Kiln with reasoning summaries turned off."`
- In `format_error_message`, before the `RuntimeError` branch: if `isinstance(exc, litellm.BadRequestError)` and `"must be verified to generate reasoning summaries"` is in `_safe_str(exc)`, return the constant. Every other `BadRequestError` still falls through to the generic message.

### 3.9 Desktop API (`app/desktop/studio_server/provider_api.py`)

- `connect_api_key` reads an optional `options` object from the payload. It must be a dict with string keys and bool values; otherwise return a 400 with "Invalid options". Default `{}`.
- For OpenAI it calls `connect_openai(parse_api_key(key_data), reasoning_summaries=options.get("reasoning_summaries") is True)`.
- `connect_openai(key: str, reasoning_summaries: bool)` saves the key and the setting only after the key check succeeds.
- The OpenAI disconnect case also sets `Config.shared().open_ai_reasoning_summaries = False`.
- The payload is an untyped `dict`, so the OpenAPI schema doesn't change and `generate_schema.sh` isn't needed. Confirm this with `check_schema.sh`.

### 3.10 Web UI (`app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte`)

Use the `kiln-ui` skill for this change.

- `Provider` gets `api_key_options?: { id: string; label: string; info: string }[]`. The OpenAI entry gets one option:
  - `id: "reasoning_summaries"`, `label: "Show reasoning summaries"`;
  - `info`: "Shows a summary of the model's reasoning for newer GPT models. OpenAI requires [organization verification](https://platform.openai.com/settings/organization/general) for this; runs fail if your organization isn't verified. To change this later, disconnect and reconnect OpenAI."
- New state `api_key_option_values: Record<string, boolean>`, reset to `{}` when the key dialog opens.
- Render the options below the fields-and-Connect row, **outside** `#api-key-fields`. `submit_api_key` reads every `<input>` in that div as a text value. Each option is a `FormElement` with `inputType="checkbox"`, `label={option.label}`, `info_description={option.info}` and `bind:value`, so the house control owns the input, label and tooltip.
- `submit_api_key` adds `options: api_key_option_values` to the POST body.
- The dialog only opens while the provider is disconnected, and disconnecting turns the setting off, so the checkbox always starts unchecked. No current-value fetch is needed. Update the functional spec's "the dialog shows the current value" line to say this.

### 3.11 Maintainer docs (branch 1 part)

In `.agents/skills/claude-maintain-models/SKILL.md`, OpenAI section, document `openai_reasoning_summary`: set it to `"auto"` on OpenAI-direct GPT-5.4+ and GPT-6+ reasoning models; it is passed through as-is and only sent when the user's setting is on. Run the `docs-sync` skill before the PR.

## 4. Branch 2 (model list, after release)

- **Tools on (F3).** Remove `supports_function_calling=False` and its comment from the OpenAI-direct providers of the ten models in §3.2, which is every model there except the two Pro models.
- **Hide `max` (F4).** Add two constants and point the OpenAI-direct providers at them. The OpenRouter and Pro providers keep their current constants.
  - `GPT_6_ASTRA_OPENAI_DIRECT_THINKING_LEVELS` = Low, Medium, High, Extra High, used by `gpt_6_astra` OpenAI.
  - `GPT_6_OPENAI_DIRECT_THINKING_LEVELS` = Off/None, Low, Medium, High, Extra High, used by `gpt_6_sol` and `gpt_6_luna` OpenAI.
  - One comment above them: `/v1/chat/completions` rejects `max` for these models with a 400 and only `/v1/responses` accepts it. LiteLLM sends a call to Responses only when tools are attached or a reasoning summary is requested, so a `max` run without either fails. Restore `max` once every call to these models goes to Responses.
  - Reword the comments on `GPT_6_1_SOL_OPENAI_THINKING_LEVELS` and on GPT-6.1 Terra's OpenAI provider to give the same reason.
- **GPT-6.1 Terra (F6).** Only if the paid check fails: add `GPT_6_1_TERRA_OPENAI_THINKING_LEVELS` = Low, Medium, High, Extra High, with a comment that tools at `none` fail on Chat Completions for this model. Point Terra's OpenAI provider at it.
- **Maintainer docs (rest of F7).** In the same skill file: no `supports_function_calling=False` for new OpenAI-direct models; when to hide `max`.
- **Model list tests.** Update any assertion in `test_ml_model_list.py` that expects tools off or `max` on these entries.

## 5. Error handling

| Case | Behavior |
|---|---|
| Unverified org, summaries on | `BadRequestError` from LiteLLM. `KilnRunError` carries the message from §3.8. No retry: `retry_classification` already treats 400s as final. |
| Other OpenAI 400s | Unchanged: generic message. Eval and data-gen logs still show `original`. |
| `store: false` with replayed reasoning | Expected to succeed (finding 7, docs). If OpenAI rejects it, paid tests catch it before ship. |
| GPT-6 Astra 403 `misalignment_policy_violation` | Not special-cased. It surfaces as today's generic provider error. |
| `options` payload malformed | 400 "Invalid options" from the connect endpoint. |

## 6. Testing

### Unit tests (agent runs them; all offline)

- **`test_litellm_adapter.py`:**
  - `build_extra_body` sends `store=False` for `ModelProviderName.openai` and not for OpenRouter or OpenAI-compatible providers.
  - `reasoning_summary` is set only when both the provider field and `LiteLlmConfig.openai_reasoning_summaries` are set (all four combinations).
  - Build test providers with `KilnModelProvider(...)`, not bare `Mock()`, which reads new fields as truthy.
  - `acompletion_checking_response` routes to `StreamingCompletion` only when `reasoning_summary` is in the kwargs.
- **`test_litellm_streaming.py`** (new, next to `litellm_streaming.py`), using synthetic `ModelResponseStream` chunks:
  - choice index remapped to 0;
  - `"\n\n"` inserted when the part number changes;
  - terminal `reasoning_items` attached to the built message;
  - `reasoning_content` joined across two items and three parts;
  - no change when there are no reasoning items.
- **`test_errors.py`:** the verification message is mapped. An unrelated `BadRequestError` still maps to the generic text.
- **`test_provider_tools.py` / `test_adapter_registry.py`:** the setting flows from `Config` to `LiteLlmCoreConfig` to `LiteLlmConfig`. Use the temp settings file from the root `conftest.py`, not a patch.
- **`test_config.py`:** the new property defaults to False.
- **Desktop `test_provider_api.py`:**
  - connect with options true, false and missing saves the setting;
  - a malformed `options` returns 400;
  - disconnect resets the setting;
  - a failed key check saves nothing.
- **Web UI:** a component test that the OpenAI dialog renders the option, that other providers don't, and that the submit body includes `options`.
- **`test_ml_model_list.py`:** the field is `"auto"` on exactly the twelve providers and `None` elsewhere.

### Offline wire tests (new `model_adapters/test_openai_responses_wire.py`)

These run **real** LiteLLM through `LiteLlmAdapter`, with `respx` intercepting HTTP and `litellm.disable_aiohttp_transport = True`, as in `test_cloudflare_litellm.py`. Return streamed bodies as `httpx.Response(200, content=<SSE bytes>, headers={"content-type": "text/event-stream"})`. Cases:

1. A tool call on a tool-enabled bridged provider (`gpt_5_4_pro`) completes. This is the dependency smoke test: it would have caught the `mcp` `ImportError` from finding 1.
2. That request goes to `/v1/responses` with `"store": false`.
3. Summaries on: the request body has `reasoning.summary == "auto"` and `"stream": true`. Summaries off: neither.
4. A reply with a message and a function call runs the tool. (Regression test for the lost tool call.)
5. A reply with two reasoning items and three summary parts produces the full `"\n\n"`-joined text in `intermediate_outputs["reasoning"]`, both non-streamed (via §3.6) and through `invoke_openai_stream`.
6. Round 2 of a streamed tool loop replays both reasoning items with `encrypted_content`.
7. A 400 with the verification message produces a `KilnRunError` whose message is §3.8's.

Fixtures for the Responses bodies and SSE events come from the research probes: `research/.../litellm-responses-support/experiments.md` and the shapes in §1.

### Paid tests (agent writes them and the commands; the team runs them with real keys)

- **Branch 1:**
  - The full paid suite across all providers.
  - New `test_openai_reasoning_summaries_paid` (in `test_thinking_level_paid.py`). It covers the twelve providers at their default level, non-streamed and streamed (`invoke_openai_stream`). It builds the adapter from `litellm_core_provider_config` with `dataclasses.replace(..., openai_reasoning_summaries=True)`, then asserts non-empty reasoning. Needs a verified org.
  - A tool loop with `store: false` on `gpt_5_4_pro`, the only tool-enabled bridged model before branch 2.
  - In `test_thinking_level_reasoning_content`, stop asserting reasoning for OpenAI-direct providers. The setting is off there, so assert only that the run succeeds, as the test already does for adaptive Anthropic models.
- **Branch 2:**
  - New `test_openai_tools_every_thinking_level_paid` over the ten providers and every available level, including `none`. This covers GPT-5.4's default and the F6 check on GPT-6.1 Terra.
  - A narration-then-tool-call prompt on each of the ten.
  - Add the ten at their default level to `STREAMING_MODELS` and `RETURN_ON_TOOL_CALL_MODELS` in `test_litellm_adapter_streaming.py`.
  - Check that streamed tool calls round-trip. Observed against a fake server: on the streaming path LiteLLM used OpenAI's item id (`fc_…`) as the tool call id instead of `call_id`. Kiln's trace and the next request stay consistent, but OpenAI's acceptance needs confirming.
- **Failure policy:**
  - If tools at `none` fail on GPT-6.1 Terra, apply §4 F6.
  - On any other model, stop and report to the user.

## 7. Release checklist

1. Branch 1 PR: unit tests, wire tests, lint and type checks, the conventions gate (expect the one H24 FAIL from §3.4, reported), the paid suite. Merge.
2. Ship the app release.
3. Branch 2 PR: OpenAI paid tests with tools on. Merge to `main` after the release is live.
4. Push to `remote_config`.

## 8. Decisions

1. **LiteLLM version: decided, `>=1.105.6,<1.106`** (finding 1). It has the tool-call fix and lacks only the invented-id fix, which Kiln doesn't hit. Not chosen: 1.106.x with an `mcp` 2.x upgrade (a separate project), and 1.106.x with LiteLLM's private `_skip_mcp_handler` argument.
2. **Non-streamed calls with summaries stream internally: decided, with an exit.** Implement §3.6 if it stays clean. "Clean" means:
   - the change stays inside `acompletion_checking_response` and `StreamingCompletion`;
   - no other caller or existing test needs reworking;
   - usage, cost and errors behave the same as the non-streamed path.

   If it isn't clean, the coding agent stops and proposes punting instead. Punting means shipping non-streamed summaries with only the last reasoning item, documenting that in a code comment, and filing the LiteLLM bug upstream.
3. **Attach the streamed reasoning items to the rebuilt message (§3.7, step 3): decided, yes.** It restores reasoning replay between tool rounds inside one run, on the streaming path. §3.6 needs it to avoid a regression. It does not carry reasoning across runs (saved conversations, `return_on_tool_call` resume, synthetic-user turns); that stays with the separate reasoning project, whose handoff prompt now notes this fix.
