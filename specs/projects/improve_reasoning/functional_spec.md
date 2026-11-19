---
status: complete
---

# Functional Spec: Improve Reasoning

## Purpose

When Kiln continues a conversation from a saved trace, the model should get its own earlier reasoning back, in exactly the form its provider requires. That keeps reasoning quality across turns and lets the provider reuse its prompt cache for the whole earlier conversation.

Today, reasoning survives only inside one run's in-memory tool loop. The saved trace keeps `content`, `reasoning_content` and `tool_calls`. Every provider's own reasoning state is lost: OpenAI encrypted reasoning items, Anthropic signed thinking blocks, Gemini thought signatures and OpenRouter `reasoning_details`. A paid probe on OpenAI showed the cost. The tool loop sends reasoning, and the next turn, loaded from the saved trace, sends none. So the whole earlier conversation misses the cache, and only the system prompt and tools are reused ([probe results](./research/openai-reasoning-order/summary.md)).

## Terms

- **Native reasoning:** the reasoning state a provider returns for replay, in the provider's own form. It is opaque to Kiln. Kiln stores it in LiteLLM's own message fields, `thinking_blocks` and `reasoning_items`, plus the provider-specific keys listed under [Provider behaviour](#provider-behaviour).
- **Readable reasoning:** the text in `reasoning_content`. For DeepSeek-style models (Fireworks, Together, Groq, Ollama, Cerebras, SiliconFlow, custom hosts) it is the real reasoning. For OpenAI, Anthropic and Gemini it is a summary or display text, and the real state is the native reasoning.
- **Trace model:** the model name and provider of the `TaskRun` that owns a trace.

## Scope

### Paths that continue from a saved trace

All three are in scope:

1. **Multi-turn:** a new user message, continuing from `prior_trace` / `parent_task_run`.
2. **`return_on_tool_call` resume:** Kiln stops when the model calls a tool the caller runs, and the caller resumes with the tool result as a new run. This reload is built into the feature, because the caller may return much later or from another process.
3. **Synthetic-user turns:** every target turn continues from the previous run's trace.

The tool loop inside one run already keeps LiteLLM's live message objects in memory. Its behaviour doesn't change, except where a provider fix below touches it.

### Providers

- **Must work:** OpenAI, Anthropic, Gemini (API and Vertex), OpenRouter.
- **Fixed as part of this project:** Groq and Ollama.
- **Must not get worse:** every other provider. That includes Fireworks, Together, Cerebras, SiliconFlow, Cloudflare, Featherless, custom OpenAI-compatible hosts, Azure and Bedrock.

### Out of scope

- **Reasoning across models.** One model's reasoning is never sent to another.
- **OpenAI reasoning order and `phase`.** The paid probe found that real replies never interleave reasoning between tool calls, that no order errors, and that `phase` doesn't change the prompt. LiteLLM's chat-to-Responses conversion stays. LiteLLM's native Responses API is not adopted.
- **Server-side OpenAI state:** `store: true`, reasoning by id, `previous_response_id`.
- **Overriding OpenAI's `reasoning.context`.** Each model keeps its default.
- **Migrating existing saved runs.**
- **UI to show reasoning held only on parent runs.**
- **Displaying native reasoning in the UI.**

## Behaviour

### 1. Saving reasoning

For every assistant message a model returns, through any path, streamed or not:

- Readable reasoning is saved in `reasoning_content`, as today.
- Native reasoning is saved alongside it, exactly as the provider returned it. Every item is kept, in the order LiteLLM gives, with nothing altered, merged or re-serialised in a way that changes its content. Signatures and encrypted blobs are saved byte for byte.
- Messages with no reasoning are saved as today. Native fields are left off, not saved as empty values.

### 2. A trace's reasoning all belongs to the trace model

All reasoning saved on a trace, readable and native, comes from that trace's own model and provider. Kiln enforces this when it builds each new run:

- **Same model:** the new run continues on the trace model (same model name and same provider). All reasoning is sent back and saved again in the new run's trace.
- **Different model:** the new run uses a different model name or provider. No reasoning from earlier messages is sent, readable or native. The new run's trace saves the earlier messages exactly as they were sent, with no reasoning. Reasoning on those older turns therefore disappears from the new run's trace. This is intended, because the trace records what the model actually saw. The original reasoning stays on the parent runs.
- **Where the earlier model comes from:** the `parent_task_run`'s model name and provider. If `prior_trace` is given without a parent run, it is treated as belonging to the current model and sent as-is. A caller who builds a trace by hand is responsible for what is in it.
- **"Same model"** means an exact match on both Kiln model name and provider. For example, Claude Sonnet 5.5 on Anthropic and on OpenRouter are different models, so switching between them strips reasoning.
- **Forking:** continuing from an earlier run on that run's model gets its reasoning back, because each run's trace is complete.

### 3. What is sent back, on the same model

- Native reasoning is sent back in the form the provider requires.
- Readable reasoning is sent back only when the message has no native reasoning, because then it is the real reasoning, as on DeepSeek-style models. When native reasoning is present, the readable text is display-only and is never sent. That stops Gemini summaries going back as unsigned thought parts, and OpenRouter Claude summaries going back as unsigned reasoning.
- Providers that reject readable reasoning on input keep having it stripped (Cerebras).

### 4. Exactness

The request Kiln sends from a saved trace must be identical to the request LiteLLM would send for the same history from the live, in-memory messages. Content, reasoning and tool calls must match token for token, in the same order. This is what lets the provider reuse its prompt cache, and the tests check it directly (see [Testing](#testing)).

When a provider change below alters what the in-run tool loop sends, the saved trace must keep matching the in-run request. An example is fixing Anthropic's doubled thinking text.

### 5. Prompt caching

- `automatic_prompt_caching` turns on by default for every run, including the first turn of a conversation. A turn can only read a cache that an earlier call wrote, so the first turn must write it too.
- **Cache markers go to Claude models only:** on Anthropic direct, and through OpenRouter. Every other provider uses its own automatic caching, and Kiln sends no markers. Today Kiln asks LiteLLM to add markers on every provider. LiteLLM then switches OpenAI GPT-5.6+ to "explicit" cache mode, and a paid check on GPT-5.6 Luna measured 0 cached tokens on turns 2 and 3 there, against a full hit with no markers. On Gemini and Vertex, LiteLLM uses the markers to create a separate stored context cache, found by reading LiteLLM's code. That cache is billed for storage and changes the request body. The synthetic user, which sets this flag today, gets both of those problems. This fix removes them.
- Cost on Anthropic: writing the cache costs 1.25× the normal input price for the cached part, and reading it costs 0.1×. A run that is never continued and has no tool loop pays the extra 25% on its input for nothing. Any second call (a tool round or a later turn) more than pays it back.
- Callers can still turn it off explicitly.

### 6. When a provider rejects replayed reasoning

The run fails. Kiln does not retry without reasoning. This is expected to be very rare. The error message states the problem, then the workaround. For example:

> The provider rejected this conversation's saved reasoning (`<provider error summary>`). This can happen after changing API keys or organizations. Using another model or provider will not send past reasoning, and work around this issue without changing keys.

This covers at least:
- OpenAI `invalid_encrypted_content`, after a key or org change;
- Anthropic invalid thinking-block signatures;
- the GPT-6 Astra 403 `misalignment_policy_violation`.

Any other provider error is reported as it is today.

### 7. Provider behaviour

| Provider | Native reasoning saved | Sent back on the same model | Change from today |
|---|---|---|---|
| OpenAI (Responses path) | `reasoning_items`: `id`, `encrypted_content`, `summary` | Through LiteLLM's conversion, with `store: false` and the encrypted content | Kept across turns; today it is dropped |
| OpenAI (Chat Completions path) | none | nothing to replay | none |
| Anthropic, adaptive and manual thinking | `thinking_blocks` with signatures, including redacted blocks | the signed blocks, unchanged | Kept across turns and on resume. Fix the doubled thinking text in streamed tool loops, if confirmed. Fix the manual-thinking resume 400, if confirmed. |
| Gemini API and Vertex | thought signatures (`provider_specific_fields`, and tool-call ids as today) | signatures only. The summary is not sent. | The summary is no longer sent as an unsigned thought part |
| OpenRouter | `reasoning_details` | top-level `reasoning_details` in the form OpenRouter documents | Today it never reaches OpenRouter. Fix the Gemini 3 tool-loop 400, and the Claude unsigned-reasoning rejection, if confirmed. |
| Groq | none, readable only | `reasoning_content`, or the field Groq accepts on input | Non-streamed reasoning is saved; today it is lost |
| Ollama | none, readable only | `reasoning`, the field Ollama reads | Today it is ignored |
| Cerebras | none | nothing; readable reasoning stays stripped | none |
| Fireworks, Together, SiliconFlow, Cloudflare, Featherless, custom | none, readable only | `reasoning_content` | none |
| Bedrock, Azure | as LiteLLM returns | as LiteLLM replays | no regression; no new work |

Provider-specific handling stays as small, contained pieces of code where LiteLLM falls short, as the Cerebras case does today. No new provider flags are added to `ml_model_list.py`.

### 8. Four errors that may exist today

The earlier research suspected four errors, none confirmed. All four are in scope:

1. Streamed Anthropic tool loops send the thinking text twice under its original signature.
2. OpenRouter never receives `reasoning_details`, which may 400 Gemini 3 tool loops on round 2 and on every resume.
3. Anthropic manual-thinking models (the 4.5 family) may 400 when resumed after a tool call, because the resumed request has no thinking block.
4. OpenRouter Claude may reject reasoning that has no signature.

Each is confirmed or ruled out with a paid call before any fix is designed. The fixes cover the ones that are real.

## Data contract

- **Assistant trace messages gain optional fields** for native reasoning. They use LiteLLM's names and shapes (`thinking_blocks`, `reasoning_items`) and the provider-specific keys we need. They are typed in Kiln's own trace types (`libs/core/kiln_ai/utils/open_ai_types.py`), so Kiln controls the format even if LiteLLM changes. The architecture fixes the exact list.
- **`reasoning_content` keeps its meaning:** the readable reasoning the UI and evals show. No new summary field is added.
- **Kiln-only fields stay Kiln-only.** Native reasoning fields are sent to providers under the rules above. The existing `KILN_ONLY_MESSAGE_FIELDS` keep being stripped.
- **The trace stays OpenAI Chat Completions–shaped.** A trace with every native field removed is still a valid conversation for any model.

## Compatibility

- **Older app versions** load new traces without errors. Their trace validation silently drops fields it doesn't know (checked against today's validation). If an old client saves a run again, its native reasoning is lost, and the next turn runs without reasoning, as today.
- **Existing saved runs** have no native reasoning. They continue as today: readable reasoning is sent on the same model, and stripped on a different one.
- **Exports:** native reasoning is not added to fine-tune or dataset exports. The fine-tune formatter copies only named fields, so no change is needed there beyond making sure that stays true.
- **Server API:** traces returned by the API include the native fields. An API caller who passes the trace back as `prior_trace` keeps its reasoning.
- **Public interface:** `invoke`, `invoke_returning_run_output`, `invoke_openai_stream` and `invoke_ai_sdk_stream` keep their signatures and return types. The only change is the new optional trace fields.

## Testing

### Offline tests (normal CI, free)

These run for every provider in the table above, with fake provider servers capturing the request LiteLLM sends (`respx`, as in `test_openai_responses_wire.py`).

- **Output:** a provider reply with native reasoning is saved to the right trace fields, exactly.
- **Input:** a reloaded trace sends the native reasoning back in the provider's form, on a new user turn and on a `return_on_tool_call` resume, streamed and not streamed.
- **Exactness:** the request built from a saved trace equals the request LiteLLM sends from the live in-memory messages for the same history.
- **Model switch:** continuing on a different model sends no reasoning and saves none.
- **Readable reasoning:** never sent when native reasoning is present, and sent when it isn't.
- **Interleaving guard:** an OpenAI reply with more than one reasoning item, or with reasoning after a tool call or message, is detected. The paid suite reports it, so we notice if a model starts interleaving.

### Paid tests (`@pytest.mark.paid`)

For each must-work provider, plus Groq, streamed and not streamed:

- **Output:** the run's trace holds native reasoning in the right fields.
- **Input:** the request actually sent on the next turn, captured through LiteLLM's logging hook, carries that reasoning back. This is checked for a new user turn and for a `return_on_tool_call` resume.
- **Sent tokens:** the captured turn-2 request is exactly turn 1's full request history, including its reasoning, plus the new turn. Nothing is dropped, reordered or changed.
- **Caching:** turn 2's cached input tokens are at least 95% of turn 1's request input tokens. The system prompt and tools total at least about 4,000 tokens, so every provider's minimum cacheable prefix is cleared. The threshold allows for providers' small end-of-prompt differences (3 tokens on OpenAI) and for caches counted in blocks.
- Providers that don't report cached tokens skip the caching assertion and still run the reasoning tests.
- **Retries:** a test retries only when its check fails, with a 5-second wait, up to 4 times. Caching is best-effort on every provider.

### Pre-release subset (`@pytest.mark.prerelease`)

Models default to the newest generation. An older model is used only where the behaviour under test exists only there, and the reason is noted.

The pre-release subset gets a new whitelist in `libs/core/kiln_ai/adapters/pytest_prerelease_whitelist.py`. Each model runs the output, input and caching tests on a new user turn:

| # | Provider | Model | Why |
|---|---|---|---|
| 1 | OpenAI | `gpt_6_luna` | Newest Luna; cheap |
| 2 | OpenAI | `gpt_6_1_sol` | Newest family |
| 3 | Anthropic | `claude_sonnet_5_5` | Signed thinking |
| 4 | Anthropic | `claude_haiku_5_5` | Second Anthropic tier |
| 5 | Gemini API | `gemini_4_argon` | Thought signatures |
| 6 | Vertex | `gemini_4_argon` | Same model, Vertex path. Skips without a Vertex project. |
| 7 | OpenRouter | `gemini_4_argon` | `reasoning_details` with Gemini signatures |
| 8 | OpenRouter | `claude_sonnet_5_5` | `reasoning_details` with Claude signatures |
| 9 | OpenRouter | `gpt_6_luna` | `reasoning_details` with OpenAI encrypted reasoning |
| 10 | Groq | `qwen_3p8_27b` | Groq reasoning fix |
| 11 | Fireworks | `glm_5_3_flash` | DeepSeek-style, no regression |
| 12 | Together | `muse_spark_open` | DeepSeek-style, no regression |
| 13 | Cerebras | `qwen_3p8_27b` | Readable reasoning stays stripped |
| 14 | Ollama | `qwen_3_8b` | Ollama fix. Skips unless a local Ollama server is running. |

The pre-release skill documentation (`.agents/skills/kiln-prerelease-check/SKILL.md`) is updated to list the new whitelist.

### Existing caching test

`libs/core/kiln_ai/adapters/model_adapters/test_prompt_caching.py` switches its OpenAI direct and OpenRouter cases from `gpt_5_4_mini` to `gpt_6_luna`. GPT-5.4 is older than the GPT-5.6 cutoff where LiteLLM starts using OpenAI's explicit cache mode, so the test couldn't catch that problem. Its assertion moves from "any cached tokens on a repeated request" to the 95% turn-2 check above.

### Manual check before merge

Before this project's PR merges, the Ollama paid tests are run once by hand against a local Ollama server, and the result is recorded in the PR.

## Open items for implementation phase 1

Phase 1 of implementation is paid confirmation, before design changes that depend on it. It may need to run on the user's machine with their keys. It covers:

- Confirming or ruling out the four errors above.
- What Groq accepts on input for reasoning (`reasoning` or `reasoning_content`).
- The exact field name and form OpenRouter needs for `reasoning_details`, for Gemini, Claude and OpenAI models.
