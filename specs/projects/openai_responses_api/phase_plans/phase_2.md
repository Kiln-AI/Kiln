---
status: complete
---

# Phase 2: Reasoning summaries in the adapter

## Overview

Let the LiteLLM adapter ask OpenAI for reasoning summaries on the twelve OpenAI-direct GPT-5.4+ and GPT-6+ providers, when a new global setting is on. The setting defaults to off and has no UI yet (Phase 3 adds it). Summaries make LiteLLM route the call to `/v1/responses`.

Two LiteLLM limits shape the reply side. Non-streamed replies keep only the last of several reasoning items, and streamed replies lose the reasoning items when `stream_chunk_builder` rebuilds the message. So `StreamingCompletion` collects the terminal chunk's reasoning items, puts them back on the rebuilt message, and rebuilds the full summary text from them. Non-streamed calls that request a summary run through `StreamingCompletion` internally, so both paths save the same text. The streamed deltas are also normalized onto choice 0, with a blank line between summary parts.

The unverified-organization 400 gets its own user-facing message.

## Steps

1. **Provider field** (`libs/core/kiln_ai/adapters/ml_model_list.py`).
   - Add to `KilnModelProvider`, next to `anthropic_summarized_thinking`, with a short comment above it:

     ```python
     # The summary mode sent to OpenAI as reasoning.summary, passed as-is. Only sent
     # when the user turned on reasoning summaries for their OpenAI connection.
     openai_reasoning_summary: str | None = None
     ```

   - Set `openai_reasoning_summary="auto"` on the `ModelProviderName.openai` provider of `gpt_6_1_sol`, `gpt_6_1_terra`, `gpt_6_astra`, `gpt_6_sol`, `gpt_6_luna`, `gpt_5_6_sol`, `gpt_5_6_terra`, `gpt_5_6_luna`, `gpt_5_5`, `gpt_5_4`, `gpt_5_4_pro` and `gpt_5_2_pro`, directly after `default_thinking_level`. Nowhere else.

2. **Setting** (`libs/core/kiln_ai/utils/config.py`). Add `"open_ai_reasoning_summaries": ConfigProperty(bool, default=False)` after `open_ai_api_key`. File-backed, not sensitive, no env var.

3. **Core config** (`libs/core/kiln_ai/adapters/provider_tools.py`).
   - `LiteLlmCoreConfig` gets `openai_reasoning_summaries: bool = False`.
   - The `ModelProviderName.openai` case passes `openai_reasoning_summaries=Config.shared().open_ai_reasoning_summaries`. This is the one new `Config.shared()` read; it FAILs the gate's `core-config-shared` check as an H24 case (waits on provider config injection). Not allowlisted; reported.

4. **Adapter config** (`libs/core/kiln_ai/adapters/model_adapters/litellm_config.py`). `LiteLlmConfig` gets `openai_reasoning_summaries: bool = False`.

5. **Registry** (`libs/core/kiln_ai/adapters/adapter_registry.py`). `litellm_core_provider_config` passes `openai_reasoning_summaries=config.openai_reasoning_summaries` into the `LiteLlmConfig` it builds.

6. **Request** (`LiteLlmAdapter.build_extra_body`). After the `store` branch:

   ```python
   if provider.openai_reasoning_summary is not None and self.config.openai_reasoning_summaries:
       # LiteLLM sends calls with reasoning_summary to /v1/responses as reasoning.summary.
       extra_body["reasoning_summary"] = provider.openai_reasoning_summary
   ```

7. **Internal streaming** (`LiteLlmAdapter.acompletion_checking_response`). When `"reasoning_summary" in kwargs`, run the call through `StreamingCompletion(**kwargs)`, drain it, and validate `stream.response` with the same checks as today. Otherwise call `litellm.acompletion(**kwargs)` as now. A one-line comment says why: non-streamed replies keep only the last reasoning item.

8. **Streaming fixes** (`libs/core/kiln_ai/adapters/litellm_utils/litellm_streaming.py`). Three private module functions, no module state:

   ```python
   def _reasoning_items_from_chunk(chunk: ModelResponseStream) -> list[ChatCompletionReasoningItem] | None
   def _normalize_reasoning_delta(chunk: ModelResponseStream, previous_part: int | None) -> int | None
   def _apply_reasoning_items(response: ModelResponse, items: list[ChatCompletionReasoningItem]) -> None
   ```

   - `_reasoning_items_from_chunk`: the first non-empty `delta.reasoning_items` among the chunk's choices.
   - `_normalize_reasoning_delta`: for each choice whose delta has `reasoning_content` and no `content` or `tool_calls`, treat `choice.index` as the summary part number, set `choice.index = 0`, and prefix `"\n\n"` to the delta's `reasoning_content` when the part number differs from the previous reasoning delta's. Returns the last part number seen (or `previous_part` if none).
   - `_apply_reasoning_items`: set `reasoning_items` on `response.choices[0].message`; if any summary part has text, set its `reasoning_content` to every part of every item, in order, each stripped, empty parts skipped, joined with `"\n\n"`.
   - `__aiter__`: track the last reasoning items and the part number in locals for that iteration; normalize each chunk before appending and yielding it; after `stream_chunk_builder`, apply the items when the result is a `ModelResponse` whose first choice is a `Choices`.

9. **Error** (`libs/core/kiln_ai/adapters/errors.py`). Add `REASONING_SUMMARY_VERIFICATION_ERROR_MESSAGE` with the text from architecture §3.8, and document it in the module docstring. In `format_error_message`, before the `RuntimeError` branch, return it when `exc` is a `litellm.BadRequestError` whose text contains `"must be verified to generate reasoning summaries"`.

10. **Handoff prompt** (`specs/research/openai-responses-api/handoff_reasoning_across_turns.md`). Item 2 and open question 5: say the within-run streaming replay is fixed in `StreamingCompletion`; saving reasoning across runs stays with that project.

11. **Existing tests.** Set `open_ai_reasoning_summaries = False` on the `Config` mocks in `test_provider_tools.py` and `test_adapter_registry.py` that feed the OpenAI case, since a bare `Mock` attribute fails `LiteLlmCoreConfig`'s bool validation. Fix any other test the new field breaks.

12. **Paid tests** (`test_thinking_level_paid.py`).
    - `test_thinking_level_reasoning_content`: for `ModelProviderName.openai` at levels other than `none`, assert only that the run succeeds, with a comment that OpenAI returns reasoning only as a summary, which is off by default.
    - New `test_openai_reasoning_summaries_paid`, parametrized over the twelve providers and over non-streamed (`invoke`) and streamed (`invoke_openai_stream`). Builds `LiteLlmAdapter` from `dataclasses.replace(litellm_core_provider_config(...), openai_reasoning_summaries=True)` and asserts non-empty `intermediate_outputs["reasoning"]`. Runs at `medium` on every provider, not the default level: four of them default to `none`, which returns no summary. Needs a verified OpenAI organization.

13. **Checks.** `uv run ./checks.sh --agent-mode` and the conventions gate on the worktree.

## Tests

Unit tests (offline):

- `test_openai_reasoning_summary_only_on_responses_capable_openai_providers` (`test_ml_model_list.py`): the field is `"auto"` on exactly the twelve OpenAI-direct providers and `None` on every other provider.
- `test_open_ai_reasoning_summaries_defaults_to_false` (`test_config.py`): the new property is `False` on a fresh config, and saves and reads back `True`.
- `test_lite_llm_core_config_openai_reads_reasoning_summaries` (`test_provider_tools.py`, parametrized True/False): the OpenAI core config carries the stored setting, using the temp settings file.
- `test_lite_llm_core_config_non_openai_ignores_reasoning_summaries` (`test_provider_tools.py`): with the setting on, an OpenRouter core config has it `False`.
- `test_litellm_core_provider_config_copies_openai_reasoning_summaries` (`test_adapter_registry.py`, parametrized True/False): the `LiteLlmConfig` built for an OpenAI run config carries the setting.
- `test_build_extra_body_reasoning_summary_needs_field_and_setting` (`test_litellm_adapter.py`, all four combinations): `reasoning_summary` is sent only when the provider field is set and the config flag is on. Providers built with `KilnModelProvider(...)`.
- `test_acompletion_checking_response_streams_when_summary_requested` (`test_litellm_adapter.py`): with `reasoning_summary` in the kwargs, the call goes through `StreamingCompletion` and the built response is returned; `litellm.acompletion` is called once with `stream=True`.
- `test_acompletion_checking_response_rejects_bad_streamed_response` (`test_litellm_adapter.py`): a streamed result that isn't a `ModelResponse` with `Choices` raises the same `RuntimeError` as the non-streamed path.
- Existing non-streamed `acompletion_checking_response` tests keep covering the path without `reasoning_summary`.
- `test_litellm_streaming.py`, with real `ModelResponseStream` chunks and the real `stream_chunk_builder`:
  - `test_reasoning_delta_moves_to_choice_zero`: a reasoning delta on choice index 1 is yielded on index 0.
  - `test_blank_line_inserted_when_summary_part_changes`: the first delta of a new part gets `"\n\n"`; later deltas of the same part and the first delta of the stream don't.
  - `test_content_and_tool_call_deltas_keep_their_index`: deltas with content or tool calls aren't touched.
  - `test_terminal_reasoning_items_attached_to_built_message`: `reasoning_items` from the terminal chunk end up on `response.choices[0].message`.
  - `test_reasoning_content_joined_across_items_and_parts`: two items with three parts give the three stripped texts joined by `"\n\n"`.
  - `test_reasoning_items_without_summary_text_keep_streamed_reasoning`: items whose summaries are empty attach but leave `reasoning_content` as built.
  - `test_no_reasoning_items_leaves_built_response_unchanged`: no items, no change.
  - `test_part_tracking_resets_on_re_iteration`: a second iteration doesn't carry the last part number over.
- `test_errors.py`:
  - `test_reasoning_summary_verification_error`: a `litellm.BadRequestError` with OpenAI's text maps to the constant.
  - `test_unrelated_bad_request_error_uses_generic_message`: any other `BadRequestError` still maps to the generic text.

Offline wire tests (`test_openai_responses_wire.py`, real LiteLLM through respx):

- `test_summaries_on_streams_to_responses_with_summary` (wire case 3, parametrized over the twelve providers): with the setting on and no tools, `invoke` sends one request to `/v1/responses` whose body has `reasoning.summary == "auto"` and `"stream": true`.
- `test_summaries_off_sends_no_summary` (wire case 3): with the setting off, a tool-less `gpt_6_1_sol` call goes to `/v1/chat/completions` with no `reasoning_summary`, `reasoning` or `stream`.
- `test_multi_part_summary_saved_in_full` (wire case 5, parametrized `invoke` / `invoke_openai_stream`): a reply with two reasoning items and three summary parts saves the full `"\n\n"`-joined text as `intermediate_outputs["reasoning"]`.
- `test_streamed_reasoning_deltas_on_one_choice_with_part_breaks` (wire case 5): through `invoke_openai_stream`, every reasoning delta is on choice 0, and their concatenation equals the saved text.
- `test_streamed_tool_loop_replays_reasoning_items` (wire case 6, parametrized `invoke` with summaries on / `invoke_openai_stream`): round 2's input has both reasoning items with their ids and `encrypted_content`, before the function call.
- `test_unverified_org_error_message` (wire case 7): a 400 with OpenAI's verification text makes `invoke` raise `KilnRunError` with the §3.8 message.

Paid tests (the team runs them):

- `test_openai_reasoning_summaries_paid` (new), and the relaxed `test_thinking_level_reasoning_content`.
- `test_openai_reasoning_summaries_at_none_paid` (new): with summaries on at thinking level `none`, each provider that offers `none` returns output and no reasoning.
