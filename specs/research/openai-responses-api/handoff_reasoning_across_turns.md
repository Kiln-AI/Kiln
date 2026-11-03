# Handoff prompt: keep OpenAI reasoning across turns

Paste everything below the line into a new agent session.

---

You're picking up a problem in Kiln's LiteLLM adapter: OpenAI reasoning state is lost between model calls. This prompt states the problem and what is already known. It does not propose a solution. Your job is to explore the options, with special attention to LiteLLM's native Responses path. Then agree a design with the user before writing code.

## Goals

1. **Maximum prompt-cache reuse** across tool rounds and across conversation turns.
2. **Correctness:** no new 400s, no silently wrong replays, and behavior that holds across every path listed below.
3. **No breaking change** to Kiln's public interface (see Constraints). Additive, optional fields are open for discussion.

You may choose ID-based state (OpenAI keeps the items and Kiln keeps ids) instead of stored encrypted reasoning, or a mix of the two. Nothing is decided.

## Background

Kiln calls OpenAI through LiteLLM's chat-to-responses conversion layer, which LiteLLM calls the responses API bridge. Kiln keeps a Chat Completions-shaped interface. A separate project is moving the newer OpenAI-direct models (GPT-5.4+, GPT-6+) onto `/v1/responses`. That project upgrades LiteLLM to 1.105.x (not 1.106.x, which needs `mcp` 2.x), sends `store: false`, turns tools on for those models, and adds an optional reasoning-summaries setting. Assume it lands first, or check its status with the user. One conflict to note up front: an ID-based design needs `store: true`, and that project's default is `store: false`.

Research for both projects lives on branch `claude/pensive-cannon-3jnl5q` under `specs/research/openai-responses-api/`. Read `summary.md` first. The deep docs most relevant to you:

- `kiln-adapter-and-public-surface/public-surface-and-trace-contract.md`, `streaming-and-ai-sdk.md`, `adapter-request-response-path.md`, `offline-probes.md`
- `litellm-responses-support/reply-and-streaming-mapping.md`, `native-responses-api.md`, `known-defects.md`, `experiments.md`
- `openai-responses-api/reasoning-and-state.md`, `streaming.md`, `data-retention-caching-pricing.md`
- `prior-art/lessons-for-kiln.md`, `failure-catalog.md`, `frameworks.md`

No live OpenAI calls were made in that research. All wire behavior was observed against local fake servers. Treat anything that needs OpenAI's real behavior as unverified.

## The problem: where reasoning state is lost today

Each item says how it is known: **read** in code, **observed** against a fake server, or **inferred**.

1. **Saved trace to the next run.** `LiteLlmAdapter.litellm_message_to_trace_message` (`libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py`) keeps only `content`, `reasoning_content` and `tool_calls` on assistant messages. `TaskRun.trace` validation drops any key the trace TypedDicts don't declare. So OpenAI reasoning items (`id`, `encrypted_content`, `summary`) never survive into a saved trace. (Read; observed: a `prior_trace` continuation carried no reasoning item.) Three paths continue from a saved trace:
   - **Multi-turn runs** (`prior_trace`, `parent_task_run`).
   - **`return_on_tool_call` resume.** This resumes mid-turn, right after the model called a tool. OpenAI says reasoning items returned with tool calls "must also be passed back", so losing them here is likely worse than losing them at a user-turn boundary. (Inferred.)
   - **Synthetic-user turns** (`libs/core/kiln_ai/synthetic_user/`). Every turn goes through a trace continuation.
2. **Streaming tool loop, within one run.** `StreamingCompletion` (`adapters/litellm_utils/litellm_streaming.py`) rebuilds each response with `litellm.stream_chunk_builder`. That drops `reasoning_items`, which LiteLLM delivers only on the terminal chunk. So the streaming path loses reasoning between tool rounds even inside one run. (Read; observed `reasoning_items: null` after the rebuild.) LiteLLM's docs tell streaming callers to collect `delta.reasoning_items` themselves. **The Responses API project fixes this one** (`specs/projects/openai_responses_api/architecture.md` §3.7): `StreamingCompletion` puts the terminal chunk's reasoning items back on the rebuilt message, so streamed tool loops replay reasoning within a run. Check that it has landed before working on this item.
3. **Non-streaming tool loop, within one run.** This path works. The live LiteLLM `Message` objects stay in the message list, and the bridge replays their `reasoning_items` on the next round. (Observed.) One exception: LiteLLM keeps only the last of several consecutive reasoning items in a reply. That LiteLLM defect is still open in 1.108.0rc1. (Read.)
4. **`phase`.** On GPT-5.4+, assistant message items carry `phase` (`commentary` or `final_answer`). OpenAI warns that dropping it can make "preambles [be] treated as final answers". LiteLLM's bridge has no `phase` handling at all in 1.106.6 (zero references), and Kiln's trace has no field for it. So it is lost even within a run. (Read.)
5. **Other providers, unverified.** Kiln's non-test code keeps no Anthropic `thinking_blocks` (with signatures) and no OpenRouter `reasoning_details`. The same trace limitation may affect Anthropic extended thinking, especially on `return_on_tool_call` resume, and OpenRouter reasoning replay. Check whether these cause errors or only lose quality, and whether they belong in scope.

## Why it matters

- **Cache and cost.** OpenAI's GPT-5.4 guide says passing chain of thought between turns gave "improved intelligence, fewer generated reasoning tokens, higher cache hit rates, and lower latency". The migration guide claims 40–80% better cache utilization on Responses than on Chat Completions, with no method published.
  - The suspected cause (inferred, not measured): within a run the model saw its reasoning, but the next turn's input omits it. The input then stops matching the cached prefix right where the reasoning was. So the previous turn's tool calls and tool results are billed uncached.
  - Uncached is 10–20× the cached rate on GPT-5.6+. Cached reads cost 0.1× input, or 0.05× on GPT-6.1 Sol and Terra.
  - Kiln already records `cached_tokens` per message (`usage_from_response`), so this can be measured.
- **Model behavior.** GPT-5.6+ default to `reasoning.context: "all_turns"` and use earlier-turn reasoning when it is replayed. Models before GPT-5.6 don't render earlier-turn reasoning by default. They do render reasoning between tool calls within a turn.
- **Not a regression.** Chat Completions never carries reasoning, and these models can't use tools on Chat Completions today. This is an improvement project.

## What is known: OpenAI

Sources are OpenAI's docs, fetched 2026-10-30 (see `openai-responses-api/`).

- **Defaults.** Responses defaults to `store: true`, which keeps data at least 30 days. Zero Data Retention (ZDR) orgs have `store` forced to false.
- **Stateless replay.** Replaying a reasoning item by `id` alone under `store: false` fails with "Item with id 'rs_...' not found". Stateless replay needs `encrypted_content`, which OpenAI returns by default in stateless mode (since about July 2026). The legacy `include: ["reasoning.encrypted_content"]` is still accepted.
- **Id plus encrypted content.** OpenAI-direct reportedly accepts both on one item under `store: false`; one third-party report says Azure rejects that. Unverified.
- **Streaming.** Take the final `encrypted_content` from `response.output_item.done`. The copy in `.added` may be incomplete.
- **Org changes.** Encrypted reasoning fails with `invalid_encrypted_content` if it is replayed under a different OpenAI organization.
- **Server-side state.** `previous_response_id` requires stored responses and still bills every prior input token. The Conversations API keeps data "until deleted" and is not ZDR-eligible.
- **Misalignment monitoring.** On GPT-6 Astra this can block Responses requests that use persisted reasoning. It returns HTTP 403 `misalignment_policy_violation`, possibly mid-stream.
- **Cache invalidation.** What changes the cached prefix: `model`, `tools`, `parallel_tool_calls`, `text.format`, `reasoning.effort`, `text.verbosity`, `context_management`.

## What is known: LiteLLM

Version notes refer to 1.102.0, which `main` uses today, and 1.106.6, the upgrade target. See `litellm-responses-support/`.

- **Bridge replay.** The bridge replays `msg["reasoning_items"]` from an assistant message, using `id`, `encrypted_content` and `summary`. Since 1.106.0 it no longer invents ids for items without one. It sends earlier function calls by `call_id` only, without OpenAI's `fc_` ids. So history with reasoning left out is accepted.
- **Native `litellm.aresponses()`.** Kiln would build `input` items and read `output` items directly, so nothing is lost in the bridge's conversion. Specifics:
  - It rewrites response ids to `resp_<base64(provider;model_id;id)>` and decodes them again on `previous_response_id`.
  - Cost is in `_hidden_params["response_cost"]`.
  - Streaming returns a typed event iterator.
  - LiteLLM's logging callback in Kiln reads `.choices` and would only log a warning on this path.
  - Going native means writing chat-history-to-items and output-to-`ModelResponse` conversions. It also means rebuilding the `ModelResponseStream` chunk stream that `invoke_openai_stream` returns.
- **Model map.** LiteLLM fetches its model map from GitHub at import unless `LITELLM_LOCAL_MODEL_COST_MAP=true`. Routing can therefore change without a Kiln release.

## What is known: other frameworks

See `prior-art/`. Every framework that moved to Responses then fixed a long run of 400 errors. Nearly all were about which item ids to send, what to do with reasoning between turns, and `store`, not about mapping fields. The patterns they converged on:

- Send items without server ids unless replaying the exact prior output.
- Set `store` explicitly.
- Use `store: false` plus encrypted reasoning for stateless or ZDR use.
- Drop reasoning that can't be replayed.
- Keep text and tool calls from one reply in one message.

How individual frameworks handle it:

- **Pydantic AI** always replays encrypted reasoning. Its maintainer says disabling it "will hurt performance significantly".
- **Agents SDK** has an id-omit policy.
- **AI SDK** defaulted to `store: true`, which broke ZDR orgs.

The failure catalog lists the error strings to write tests for.

## Constraints

- **Public interface stays.** That covers:
  - `invoke` / `invoke_returning_run_output` returning `TaskRun` / `RunOutput`;
  - `invoke_openai_stream` yielding LiteLLM `ModelResponseStream` chunks;
  - `invoke_ai_sdk_stream` yielding `AiSdkStreamEvent`s;
  - `TaskRun.trace` and `prior_trace` in OpenAI chat format (`ChatCompletionMessageParam`).
- **Model switching.** A conversation can continue on a different model or provider. Any OpenAI-only state must be stripped or ignored when the next call isn't OpenAI. `KILN_ONLY_MESSAGE_FIELDS` and `sanitize_messages_for_provider` (`libs/core/kiln_ai/utils/open_ai_types.py`) are the existing mechanism for fields that must not reach a provider.
- **Key or org changes.** A user can change their OpenAI key or org between turns.
- **Old clients.** Older app versions read saved traces too, so any new trace field must be safe for them to load. Check how they validate traces.
- **Repo rules.** Follow `AGENTS.md`. It covers the conventions skill, test guide and checks.

## Open questions to answer

1. Measure cache reuse across tool rounds and turns for each option, with a paid OpenAI key, using `cached_tokens`. Does dropping reasoning at a turn boundary actually lose the cached tool segment?
2. ID-based vs encrypted vs hybrid: which gives the best cache reuse and quality under `store: true` and under `store: false`, and what does each need from Kiln's trace?
3. Does an ID-based design fit Kiln? Things to weigh:
   - data retention at OpenAI;
   - ZDR orgs;
   - item expiry;
   - forking a conversation from the same parent run more than once;
   - editing history;
   - switching models.
4. LiteLLM native `aresponses()` vs the bridge for OpenAI-direct only. What does native buy here (phase, all reasoning items, exact output replay, streaming `output_item.done`), and what does it cost to rebuild the chat-format outputs?
5. Is the streaming within-run loss fixable inside the bridge path, by collecting `delta.reasoning_items` from the terminal chunk?
6. Does `return_on_tool_call` resume need different handling from user-turn continuation?
7. Are the Anthropic thinking-block and OpenRouter `reasoning_details` gaps real problems, and do they belong in this project?
8. How should errors be handled: `invalid_encrypted_content`, missing or expired items, and the GPT-6 Astra 403?

## Getting started

1. Check out `claude/pensive-cannon-3jnl5q`, or read the research from it, and read `specs/research/openai-responses-api/summary.md`.
2. Read the files named above to confirm the current behavior yourself. Treat the research as leads to verify. Code may have moved since 2026-10-30.
3. Ask the user for an OpenAI API key before making any paid call.
4. Bring the user options with tradeoffs before choosing. They expect to use the repo's `/spec` process for the design.
