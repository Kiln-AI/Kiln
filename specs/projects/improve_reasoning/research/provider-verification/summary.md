# Provider verification: paid calls for the improve-reasoning design

- **Date:** 2026-11-19
- **LiteLLM:** 1.105.7
- **Kiln:** branch `claude/improve-reasoning` at `47ac5aaca`. No Kiln source was changed.
- **Ollama:** 0.40.16 (local).
- **Script:** [probe.py](./probe.py). It passes `ruff check`, `ruff format --check` and `ty check`.
- **Raw data:** [raw_results.json.gz](./raw_results.json.gz). Signatures, encrypted blobs and thought-signature ids are cut to 40 characters. Prompt text longer than 1,500 characters is cut to 300.
- **Spend:** about US$1.80. That figure uses LiteLLM's cost per call, plus OpenRouter's reported `usage.cost` for raw calls. It includes about US$0.19 of runs that were thrown away (see [Caveats](#caveats)).

## Models

| Kiln model | Provider | Exact model id | Why this model |
|---|---|---|---|
| `claude_sonnet_5_5` | Anthropic | `claude-sonnet-5-5` | Newest Sonnet. Adaptive thinking. |
| `claude_opus_4_5` | Anthropic | `claude-opus-4-5-20251101` | Older model, used on purpose. Kiln uses Anthropic's manual thinking mode (`thinking: {type: enabled, budget_tokens: 4096}`) only on the 4.5 generation, and the suspected resume 400 belongs to that mode. |
| `claude_sonnet_5_5` | OpenRouter | `anthropic/claude-sonnet-5.5` | |
| `gemini_4_argon` | Gemini API | `gemini-4-argon` | |
| `gemini_4_argon` | OpenRouter | `google/gemini-4-argon` | |
| `gpt_6_luna` | OpenRouter | `openai/gpt-6-luna` | Question 5 only |
| `qwen_3p8_27b` | Groq | `qwen/qwen3.8-27b` | Newest reasoning model on Groq in the list |
| (none) | Ollama | `qwen3.5:4b` | Not in Kiln's list. Kiln runs it as an untested custom Ollama model. It was the newest local thinking model with tool support that the user could install here; `qwen3:8b` failed to download (`{"error":"EOF"}` on "pulling manifest"). |

## Short answers

| # | Question | Verdict | Who causes it | Recommended Kiln action |
|---|---|---|---|---|
| 1 | Doubled thinking text in streamed Anthropic tool loops | **Confirmed**, but Anthropic accepts it and ignores the text | LiteLLM | None for errors. Upstream report. |
| 2 | Anthropic resume after a tool call 400s | **Ruled out** on Sonnet 5.5 and Opus 4.5, with and without replayed thinking | none | None. Replaying `thinking_blocks` works. |
| 3 | OpenRouter Gemini 400 without `reasoning_details` | **Ruled out**. But the reasoning is silently dropped today. | LiteLLM (doesn't send `reasoning_details` back) | Kiln fix in both paths: send top-level `reasoning_details`. Your call, because it is a silent loss and not an error. |
| 4 | OpenRouter rejects unsigned Claude reasoning | **Ruled out**. It is silently dropped instead. | LiteLLM | Same as 3. |
| 5 | Streamed `reasoning_details` fragments | **Merge fragments that share `type` and `index`.** That gives the non-streamed shape. | For Claude, OpenRouter itself | Kiln: accumulate and merge. Upstream report to OpenRouter: it ignores its own streamed Claude signature on replay. |
| 6 | Gemini signed replay, and the unsigned summary part | Signed replay **confirmed** to work. The summary part has **no measurable effect**. | n/a | None. Don't strip `reasoning_content` on Gemini. |
| 7 | Groq loses reasoning | **Confirmed**, and worse: **streamed tool loops and multi-turn after a streamed turn 400 today** | LiteLLM (renames on stream, doesn't rename back) and Kiln (reads only `reasoning_content`) | Kiln fix in both paths: send `reasoning`, never `reasoning_content`; save `message.reasoning`. Upstream report. |
| 8 | Ollama ignores replayed reasoning | **Confirmed** | Kiln's routing choice (`openai/` route) | Kiln fix in both paths: send `reasoning` instead of `reasoning_content` on Ollama. |
| 9 | Turn-2 cache share ≥ 95% | **Anthropic: met** (99.98%). **Gemini: 79%, not met**, because Gemini caches about 2,000 tokens less than each earlier request. | Gemini's own caching | Anthropic: none. Gemini: change the test threshold or prompt size (see [9](#9-core-plan-sanity-check-caching-across-turns)). |

## Method

All Kiln-path runs use `LiteLlmAdapter` exactly as the paid tests in `test_litellm_adapter_streaming.py` build it:
- `PromptGenerators.SIMPLE` and the four built-in math tools;
- `invoke` for non-streamed runs and `invoke_openai_stream` for streamed runs;
- `AdapterConfig(return_on_tool_call=True)` for resumes;
- `prior_trace` for continuations.

The Ollama adapter gets its config from Kiln's `litellm_core_provider_config`, which adds the `/v1` base URL and placeholder key the way the adapter registry does. Kiln settings are redirected to a temporary file. `KILN_SKIP_REMOTE_MODEL_LIST=true` is set.

**Capture:**
- A LiteLLM `CustomLogger` is appended to `litellm.callbacks`. It records `kwargs["additional_args"]["complete_input_dict"]` in `log_pre_api_call`: the exact provider body.
- Kiln's `build_completion_kwargs` is wrapped to keep each round's kwargs, which include the live `Message` objects.
- Kiln's `acompletion_checking_response` and the stream's `_validate_response` are wrapped to keep each live LiteLLM response.
- Streamed runs also keep the raw LiteLLM chunks.
- Usage is read from `usage.prompt_tokens`, `prompt_tokens_details.cached_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` and `completion_tokens_details.reasoning_tokens`.

**Replays:** these use `litellm.acompletion` with a captured round's kwargs. The live `Message` objects are replaced by `json.loads(json.dumps(message.model_dump(exclude_none=True)))`, then changed per variant. Question 5 and the Groq raw check call the provider directly with `httpx`, so LiteLLM can't change the request.

**Prompt:** the task instruction is the paid tests' math instruction. The user prompt is a bakery word problem with about eight dependent steps; the answer is 100.45. Question 9 adds about 4,500 tokens of unrelated handbook rules to the system prompt. That gives a system prompt plus tools of about 7,100 tokens on Gemini and 9,400 on Anthropic.

**Thinking levels:** Anthropic used `high`. At `medium`, Sonnet 5.5's adaptive thinking returned no thinking blocks on an easier first prompt. Opus 4.5 at `high` was sent `thinking: {type: enabled, budget_tokens: 4096}` (manual mode). OpenRouter Gemini used `low` (Kiln's default) and `high`. OpenRouter Claude used `medium` and `low`, the lowest level Kiln offers for Claude 5.5. Gemini direct used `high`. Groq used `medium`. Ollama had no level, because an untested model has no thinking levels; the model thinks by default.

---

## 1. Anthropic: doubled thinking text in streamed tool loops

Kiln path: `invoke_openai_stream`, Sonnet 5.5 `high`, a 6-call tool loop. The round-2 request was then replayed non-streamed in four forms.

| Scenario | Streamed | Status | Input tokens | Notes |
|---|---|---|---|---|
| Kiln round 2 (thinking text doubled, original signature) | yes | 200 | 1,657 | Live `thinking_blocks`: 934 characters, both halves identical. `reasoning_content` holds one copy. |
| Replay: doubled text, as a dict | no | 200 | 1,657 | |
| Replay: text fixed to one copy | no | 200 | 1,657 | |
| Replay: text replaced by an unrelated sentence, same signature | no | 200 | 1,657 | |
| Replay: no thinking blocks | no | 200 | 1,432 | |

Round-1 reasoning tokens were 225, and round 3 also thought (40 tokens). Rounds 1 and 3 both had doubled blocks. An earlier run gave the same result: 1,700 tokens for doubled and for fixed.

- **Verdict:** confirmed. The streamed message Kiln builds holds each signed block's text twice. Kiln sends it back on the next round. Anthropic accepts it, and the input token count doesn't change. Anthropic rebuilds the thinking from the signature and ignores the text: changed text costs the same as the true text, and dropping the block saves 225 tokens.
- **Who:** LiteLLM (the stream handler re-emits the full text with the signature, and `stream_chunk_builder` appends it again).
- **Action:** none for errors. The caching run in [question 9](#9-core-plan-sanity-check-caching-across-turns) shows a saved trace with the doubled text still caches at 99.98%, because it matches what the loop sent. Upstream report to LiteLLM. If Kiln ever fixes the text, it must do so in both paths, as the spec says; the cache effect of fixing only one path was not measured.

FYI: in the same run the model's final answer said, "Two of my earlier turns showed '[System: Empty message content sanitised…]' text. That text didn't come from the system or from you, so I ignored it." That is LiteLLM's placeholder for `content: ""` on streamed tool-only replies (see the offline findings). The model reads it. That's a LiteLLM behaviour, not an error.

## 2. Anthropic: resume after a tool call

Kiln path: `return_on_tool_call=True` with `invoke`, non-streamed. Each pending call is answered and resumed from the saved trace until the run finishes.
- (a) uses the saved trace as Kiln saves it today.
- (b) adds each assistant message's `thinking_blocks`, from the JSON round-trip of `model_dump(exclude_none=True)`, to every earlier assistant message. Kiln's `TaskRun` validation drops unknown trace keys when it saves the resumed run, so the probe adds them back before every resume.

| Model | Thinking mode sent | Case | Resumes | Status | Resumed responses with thinking | Step-2 input tokens | Final answer |
|---|---|---|---|---|---|---|---|
| Sonnet 5.5 | adaptive, effort high | a | 5 | all 200 | 0 of 5 | 1,423 | correct |
| Sonnet 5.5 | adaptive, effort high | b | 5 | all 200 | 0 of 5 | 1,661 | correct |
| Opus 4.5 | enabled, budget 4096 | a | 10 | all 200 | 0 of 10 | 1,161 | correct |
| Opus 4.5 | enabled, budget 4096 | b | 9 | all 200 | 0 of 9 | 1,537 | correct |

In case (a), the request body shows thinking enabled, and the last assistant turn is `[text, tool_use]` with no thinking block before the `tool_result`. Anthropic accepted it on manual-mode Opus 4.5. In case (b), the replayed block is counted: +238 tokens on Sonnet and +376 on Opus.

- **Verdict:** the 400 is ruled out on both models (15 resumed calls in case a, 14 in the final case b, plus 15 from a first case b run that replayed only the newest block). No resumed response, in either case, held new thinking. Inside one run, Sonnet sometimes thinks after a tool result (question 1, round 3; question 4, round 3). So "thinking silently off after a resume" stays **inconclusive**. Replaying the blocks did not bring thinking back in these samples. On Opus 4.5 in manual mode, no thinking after a tool result is the documented behaviour anyway.
- **Who:** none. The provider accepts both forms.
- **Action:** none. Saving and replaying `thinking_blocks`, as decided, works on resume.

## 3. OpenRouter: Gemini 4 Argon tool loops

Kiln sends `reasoning_effort`, `reasoning: {enabled: true}`, `usage: {include: true}` and a provider order.

| Level | Scenario | Streamed | Status | Input tokens |
|---|---|---|---|---|
| low | tool loop, 12 calls | no | all 200 | round 2: 720 |
| low | round-2 replay: as LiteLLM sends it / no reasoning / + top-level `reasoning_details` / planned shape | no | all 200 | 720 / 720 / 720 / 720 |
| low | tool loop, 12 calls | yes | all 200 | |
| low | `return_on_tool_call`, 10 resumes | no | all 200 | |
| low | continuation from saved trace / + `reasoning_details` / planned shape | no | 200 / 200 / 200 | 1,616 / 1,660 / 1,660 |
| high | tool loop, 11 calls (round 1: 519 reasoning tokens) | no | all 200 | round 2: 577 |
| high | round-2 replay: as sent / none / + `reasoning_details` / planned | no | all 200 | 577 / 577 / **1,096** / **1,096** |
| high | tool loop, 11 calls | yes | all 200 | |
| high | `return_on_tool_call`, 10 resumes | no | all 200 | |
| high | continuation / + `reasoning_details` / planned | no | 200 / 200 / 200 | 1,381 / **1,940** / **1,940** |

"Planned shape" means top-level `reasoning_details`, with no `provider_specific_fields` and no `reasoning_content`. Each Gemini reply carries a `reasoning.encrypted` item whose `id` is the tool-call id (the signature, 224–2,800 characters). At `high` it also carries a `reasoning.text` item (729 characters on round 1). The `low` level was also run once before, with the same result (all 200, round-2 variants equal at 577).

- **Verdict:** the 400 is ruled out: tool round 2, resume and continuation all work without `reasoning_details` (0 errors in about 120 calls, over both levels and the earlier `low` run). But today the reasoning never reaches the model. What LiteLLM sends today costs exactly the same tokens as sending nothing. A top-level `reasoning_details` adds 519 tokens, which equals round 1's reasoning tokens.
- **Who:** LiteLLM. It puts `reasoning_details` in `provider_specific_fields` and sends that object back as an unknown key, which OpenRouter ignores.
- **Action:** a Kiln fix in both paths: send top-level `reasoning_details`, as in the offline plan. Both shapes were accepted; the planned shape gives the same tokens as adding the key. This is a silent loss, not an error. Under the decided rule ("deviate only to fix an error a paid call confirms"), whether to make this change is your call.

## 4. OpenRouter: Claude Sonnet 5.5 with thinking on

| Level | Scenario | Streamed | Status | Input tokens |
|---|---|---|---|---|
| medium | tool loop, 6 calls (round 1: 233 reasoning tokens) | no | all 200 | round 2: 1,423 |
| medium | round-2 replay: as sent (plain `reasoning_content`, no signature) / none / + `reasoning_details` / planned | no | all 200 | 1,423 / 1,423 / **1,656** / **1,656** |
| medium | tool loop | yes | all 200 | |
| medium | `return_on_tool_call`, 7 resumes | no | all 200 | |
| medium | continuation / + `reasoning_details` / planned | no | 200 / 200 / 200 | 2,274 / **2,507** / **2,507** |
| low | tool loop, 9 calls (round 1: 170 reasoning tokens) | no | all 200 | round 2: 1,074 |
| low | round-2 replay: as sent / none / + `reasoning_details` / planned | no | all 200 | 1,074 / 1,074 / **1,244** / **1,244** |
| low | tool loop | yes | all 200 | |
| low | `return_on_tool_call`, 6 resumes | no | all 200 | |
| low | continuation / + `reasoning_details` / planned | no | 200 / 200 / 200 | 1,987 / **2,157** / **2,157** |

- **Verdict:** rejection is ruled out. OpenRouter neither rejects nor uses the unsigned plain reasoning LiteLLM sends. It drops it silently, within a run and on resume. Top-level `reasoning_details` is used: the token increase equals round 1's reasoning tokens exactly, at both levels.
- **Who:** LiteLLM, as in question 3.
- **Action:** same as question 3. For streamed runs, see question 5.

## 5. OpenRouter: streamed `reasoning_details`

Raw `httpx` calls to OpenRouter: the same body sent non-streamed and streamed, then a round-2 replay of the streamed reply. Through LiteLLM's chunk objects, the fragments are visible on `delta.reasoning_details` (question 3 high, question 4), and `stream_chunk_builder` drops them, as the offline research found.

| Model | Non-streamed array | Streamed fragments | Merged by `type` + `index` | Round-2 replay input tokens: as-is / merged / none |
|---|---|---|---|---|
| Gemini 4 Argon (`reasoning: {enabled: true}`) | 1 × `reasoning.encrypted` (index 0, `id` = tool-call id, 280-char `data`) | 1 fragment, same shape | 1 item, unchanged | 575 / 575 / 575 (no thinking text at this setting) |
| Claude Sonnet 5.5 (`effort: medium`) | 1 × `reasoning.text` (index 0, 666-char text, 1,691-char signature) | 43 × `reasoning.text`, index 0. Text deltas of 2–24 characters; the last fragment has only the signature. | 1 `reasoning.text` item with the joined text and the signature, the same shape as non-streamed | 1,430 / 1,430 / 1,430 |
| GPT-6 Luna (`effort: medium`) | `reasoning.summary` (index 0, 477 chars) + `reasoning.encrypted` (index 1, `id` `rs_…`, 3,392-char data) | 70 fragments: `reasoning.summary` deltas at index 0, then one `reasoning.encrypted` at index 1 | 2 items, the same shape as non-streamed | **415 / 415** / 384 |

Claude, checked further (3 streamed and 3 non-streamed replies):

| Replay of the round-1 reply | Input tokens, with reasoning | Without |
|---|---|---|
| non-streamed item | 1,660 / 1,256 / 1,617 | 1,431 / 1,072 / 1,430 |
| non-streamed item with its text emptied | 1,617 | 1,430 |
| streamed, merged | 1,380 / 1,423 / 1,425 | 1,380 / 1,423 / 1,425 |
| streamed, as-is | 1,380 / 1,423 / 1,425 | same |
| streamed, merged, text emptied | 1,425 | same |
| streamed, merged, signature removed | 1,425 | same |

All of these returned 200.

- **Verdict:** merge fragments that share `type` and `index`. Join the `text`, `summary` and `data` strings, and keep the first non-empty `id`, `format` and `signature`. That rebuilds exactly the non-streamed shape for all three models. OpenRouter also accepted the fragments as-is with the same effect (Luna). But on Claude, OpenRouter ignores streamed reasoning in every form (3 of 3 samples), while it uses the non-streamed item even with the text emptied. So it reads the signature, and the streamed signature doesn't work on replay.
- **Who:** OpenRouter, for the Claude streamed case.
- **Action:** Kiln: accumulate the fragments in `StreamingCompletion` and save them merged, so streamed and non-streamed traces have one shape. Upstream report to OpenRouter about streamed Claude signatures. Until that is fixed, streamed Claude runs on OpenRouter lose their reasoning across rounds and turns, whatever Kiln sends.

## 6. Gemini API: signed replay and the unsigned summary part

Gemini 4 Argon, `high`, long system prompt, a 12-call tool loop. Turn 2 is a new user message from the saved trace, with the native fields restored as in [question 9](#9-core-plan-sanity-check-caching-across-turns). Two samples: turn 1 non-streamed, and turn 1 streamed (turn 2 runs on the same path as turn 1).

| Turn-2 variant | Streamed | Status | Input tokens | Cached tokens | Answer |
|---|---|---|---|---|---|
| restored (signatures + `reasoning_content`, as LiteLLM sends live) | no / yes | 200 / 200 | 9,664 / 9,729 | 7,024 / 7,024 | correct |
| restored, same request again | no / yes | 200 / 200 | 9,664 / 9,729 | 7,615 / 7,680 | correct |
| restored without `reasoning_content` (no unsigned thought part) | no / yes | 200 / 200 | **9,664 / 9,729** | 7,615 / 7,680 | correct |
| restored without `provider_specific_fields` (signatures) | no | 200 | 9,408 | 7,024 | correct |
| today's saved trace | no / yes | 200 / 200 | 9,408 / 9,294 | 7,024 / 7,024 | correct |

Reasoning tokens on turn 2 ranged from 138 to 563, with no pattern by variant.

- **Verdict:** signed replay is confirmed. A saved dict with `provider_specific_fields.thought_signatures` and the tool-call ids is accepted. The model gets the earlier thoughts back: +256 tokens non-streamed, +435 streamed, against today's trace. Removing `reasoning_content` changed nothing measurable: the same input tokens, the same cache hit and correct answers. The body without it differs at the first assistant message, yet it cached the same as the repeat. So Gemini drops the unsigned thought part before counting and caching.
- **Who:** n/a.
- **Action:** none. There is no error to fix, so under the decided rule Kiln keeps sending what LiteLLM sends. Gemini tool-only messages already keep their signatures inside the tool-call ids, so today's trace only lost the final answer's text signature.

## 7. Groq: Qwen 3.8 27B

Kiln sends `reasoning_effort: medium` and nothing else for reasoning (no `reasoning_format`). Groq's raw reply puts the reasoning in a `reasoning` field (raw `httpx` check: message keys `content, reasoning, role, tool_calls`).

| Scenario | Streamed | Status | Verbatim error | Input tokens |
|---|---|---|---|---|
| Kiln tool loop, 11 calls | no | all 200 | | round 2: 1,158 |
| — saved trace `reasoning_content` | no | | | empty on all 11 assistant messages |
| — `intermediate_outputs["reasoning"]` | no | | | missing (`{}`) |
| — live LiteLLM message | no | | | `message.reasoning` holds 815 characters; `reasoning_content` is `None` |
| Kiln tool loop | **yes** | **400 on round 2** | `GroqException - {"error":{"message":"'messages.2' : for 'role:assistant' the following must be satisfied[('messages.2' : property 'reasoning_content' is unsupported)]","type":"invalid_request_error"}}` | |
| Round-2 replay: no reasoning / `reasoning` / `reasoning_content` / both | no | 200 / 200 / 400 / 400 | same error | 861 / **1,158** / – / – |
| Round-2 replay: no reasoning / `reasoning` / `reasoning_content` / both | yes (turn 1) | 200 / 200 / 400 / 400 | same error | 854 / **1,226** / – / – |
| Streamed answer with no tools, then a new turn from its saved trace | yes | **400** | same error | |
| Non-streamed answer with no tools, then a new turn from its saved trace | no | 200 | | 139 (no reasoning was saved) |

Round-1 reasoning tokens were 297 non-streamed and 372 streamed. Those equal the `reasoning` increases (+297, +372).

- **Verdict:** confirmed, and worse than expected.
  - Non-streamed: the reasoning is lost from the saved trace and from `intermediate_outputs`. The in-run non-streamed loop still sends it correctly as `reasoning`, because LiteLLM keeps it as an extra attribute on the live message.
  - Streamed: Kiln's tool loop fails on round 2 today. Any multi-turn continuation after a streamed turn also fails.
  - Groq reads `reasoning` and rejects `reasoning_content`.
- **Who:**
  - LiteLLM renames streamed `delta.reasoning` to `reasoning_content` (`llms/groq/chat/transformation.py:357-363`), and its Groq message transform doesn't rename it back on input. It also leaves non-streamed `reasoning` as an unmodelled extra attribute.
  - Kiln reads only `reasoning_content` when it saves.
  - Groq itself is consistent: one field in, the same field out.
- **Action:** a Kiln fix in both paths:
  - On Groq, every outbound assistant message (live and saved) sends `reasoning`, never `reasoning_content`.
  - On save, read `message.reasoning` when `reasoning_content` is empty.
  - Report upstream to LiteLLM.
  - This is a confirmed error, so it fits the decided rule. Kiln's paid streaming tests have no Groq case, which is probably why it wasn't caught.

## 8. Ollama (local, `qwen3.5:4b`, Ollama 0.40.16)

| Scenario | Route | Status | Input tokens (`prompt_tokens` = Ollama's prompt eval count) | Fields sent on the assistant message |
|---|---|---|---|---|
| Kiln tool loop, 7 calls | `openai/` + `/v1` (Kiln) | all 200 | round 2: 815 (751 cached) | `content, reasoning_content, role, tool_calls` (from the live message) |
| — saved trace | | | | `reasoning_content` saved on all 7 assistant messages (196–10,047 characters) |
| Round-2 replay: no reasoning | `openai/` | 200 | 815 | `content, role, tool_calls` |
| Round-2 replay: `reasoning_content` | `openai/` | 200 | **815** | `+ reasoning_content` |
| Round-2 replay: `reasoning` | `openai/` | 200 | **1,111** | `+ reasoning` |
| Round-2 replay: both | `openai/` | 200 | 1,111 | `+ reasoning, reasoning_content` |
| Kiln continuation from saved trace | `openai/` | 200 | 1,733 (748 cached) | |
| Round-2 replay: live message as a dict | `ollama_chat/` (native) | 200 | **1,259** | `content, images, role, thinking, tool_calls` |
| Round-2 replay: no reasoning | `ollama_chat/` | 200 | 813 | `content, images, role, tool_calls` |
| Round-2 replay: `reasoning_content` | `ollama_chat/` | 200 | 1,259 | LiteLLM sends it as `thinking` |
| Round-2 replay: a `thinking` key on the dict | `ollama_chat/` | 200 | 813 | LiteLLM drops the key |

- **Verdict:** confirmed. On Kiln's route, Ollama ignores the replayed reasoning (815 with or without it) and reads `reasoning` (+296). LiteLLM's native `ollama_chat/` provider sends the reasoning as Ollama's native `thinking` field, which Ollama reads (+446). Ollama on `/v1` also reports cached tokens, which may be useful for the caching tests.
- **Who:** Kiln's routing choice. On the generic `openai/` provider, LiteLLM forwards `reasoning_content` as-is, which is correct for a generic provider. Ollama's OpenAI-compatible API documents and reads only `reasoning`.
- **Action:** a Kiln fix in both paths: on Ollama, send `reasoning` instead of `reasoning_content` on outbound assistant messages, live and saved. Moving to `ollama_chat/` would also fix it, but it would change much more (response formats, json_schema), so a rename is the smaller change.

## 9. Core plan sanity check: caching across turns

Turn 1 is a tool loop with the long system prompt. Turn 2 asks a follow-up from the saved trace.
- **restored:** each assistant message is replaced by the JSON round-trip of its live `model_dump(exclude_none=True)`, keeping only `content`, `tool_calls`, `reasoning_content`, `thinking_blocks`, `reasoning_items` and `provider_specific_fields`.
- **today:** the trace exactly as Kiln saves it.

There is a 5-second wait before each turn-2 call. "Share" means turn-2 cached tokens ÷ turn 1's last request input tokens.

| Provider | Cache markers | Turn 1 | Turn-1 last input | Turn-2 variant | Input | Cached | Share |
|---|---|---|---|---|---|---|---|
| Anthropic Sonnet 5.5 | on | 5 calls, non-streamed | 10,712 | restored | 11,058 | 10,710 | **99.98%** |
| | | | | restored, again | 11,058 | 11,054 | 103% |
| | | | | today | 10,731 | 9,439 | 88.1% |
| Anthropic Sonnet 5.5 | on | 11 calls, streamed | 10,600 | restored | 10,892 | 10,598 | **99.98%** |
| | | | | restored, again | 10,892 | 10,888 | 103% |
| | | | | today | 10,753 | **0** | 0% |
| Gemini 4 Argon (API) | off (planned design) | 12 calls, non-streamed | 8,933 | restored | 9,664 | 7,024 | **78.6%** |
| | | | | restored, again | 9,664 | 7,615 | 85.2% |
| | | | | today | 9,408 | 7,024 | 78.6% |
| Gemini 4 Argon (API) | off | 12 calls, streamed | 8,839 | restored | 9,729 | 7,024 | **79.5%** |
| | | | | restored, again | 9,729 | 7,680 | 86.9% |
| | | | | today | 9,294 | 7,024 | 79.5% |

Anthropic `prompt_tokens` include cache reads and writes. On the first restored call, 344 and 290 tokens were written, which is the new user turn.

**Exactness check from the captured bodies:**
- **Anthropic:** turn 1's last request is an exact prefix of the restored turn 2. The only difference is the `cache_control` marker moving from the last tool result to the new last message. That holds streamed too, with the doubled thinking text.
- **Anthropic, today's trace:** differs at the first assistant message, where the thinking is missing.
- **Gemini:** both the restored and today's turn 2 extend turn 1's last request exactly. On tool-only replies the signatures ride in the tool-call ids.

- **Verdict:**
  - **Anthropic:** confirmed. The decided rule gives a full cache hit. Today's trace loses the history. In the 11-call streamed run it lost everything, even the system prompt. Kiln marks only the last message, and Anthropic looks back at most 20 content blocks from a marker, so after a long loop it never reaches the system-prompt cache entry.
  - **Gemini:** the request is exact, but the 95% target is not met. In every call, inside turn 1 too, Gemini cached about 2,000 tokens less than the previous request's input (round 3 cached 5,801 after a 7,850-token round 2, and so on; the repeats are 9,664 − 2,049 and 9,729 − 2,049). The limit is Gemini's implicit caching, not the replay.
- **Who:** Anthropic: none. Gemini: the provider.
- **Action:**
  - Anthropic: none beyond the planned design.
  - Gemini: the spec's paid caching test can't pass at 95% with a prompt this size. Either make the Gemini test prompt much larger (the same 2,049-token gap is 5% at about 41,000 tokens), or assert `cached ≥ turn-1 last input − 2,100` for Gemini. This is a spec decision for you.
  - Separately, a second cache marker (for example on the system prompt) would keep today's Anthropic fallback from dropping to 0 on long loops. With exact replay that fallback isn't needed.

---

## Caveats

- **Sample sizes are small.** Most cells are one call. The resume chains give 6–11 calls each. The OpenRouter Claude streamed finding has 3 samples. Gemini caching has 2 turn-1 runs. Reasoning-token counts vary widely between identical requests.
- **Mid-turn thinking is rare and random.** Sonnet thought after a tool result in 2 of the in-run loops and in none of the 44 resumed calls. That is too few to say whether resuming suppresses it.
- **Discarded runs, not in the raw data:**
  - Question 1 at `medium` returned no thinking, and one `high` run came before the control replays were added (doubled = fixed = 1,700 tokens). Each new run overwrote the section's file.
  - Question 2 case (b) was first run replaying only the newest block. It is kept as `q2_anthropic_resume` case b, and `q2_anthropic_resume_b_fixed` is the correct run.
  - Question 3 `low` was first run alone, with the same results.
- **Question 4's section cost** in the raw file (0.49) is cumulative with question 3, because both ran in one process. Question 4 alone was about 0.26.
- **Ollama:** the version changed from 0.34.0 to 0.40.16 during the session, when the user restarted it. All Ollama results are from 0.40.16. `qwen3.5:4b` is not in Kiln's model list, so Kiln ran it as an untested custom model with no thinking level.
- **Not tested:**
  - Vertex.
  - OpenAI direct (covered by the earlier probe).
  - Streamed Anthropic resumes.
  - The cache effect of fixing the doubled text in only one path.
  - Whether Kiln sends Anthropic's interleaved-thinking header.
- **Gemini through OpenRouter at `low`:** no reasoning fragments were seen on LiteLLM's chunk objects in Kiln's streamed loop. The raw stream in question 5 (no effort set) carried one encrypted fragment. Where that fragment goes in LiteLLM's streamed path at `low` was not checked.
