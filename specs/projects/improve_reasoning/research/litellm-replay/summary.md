# LiteLLM 1.105.7: saving and replaying native reasoning as plain dicts

Date: 2026-11-18. LiteLLM 1.105.7 (`.venv/lib/python3.13/site-packages/litellm`, paths below are relative to it).
Kiln: branch at `d998a09` (main + improve-reasoning spec). No Kiln source was changed.

Probes: the captured output of each probe is in `./probes/*.out`. The probe scripts themselves are not committed, because the repo's lint and type checks cover `specs/` and these were throwaway scripts. The method below is enough to rebuild them. The table names the scripts each `.out` came from.

| Script | Covers |
|---|---|
| `harness.py` | Shared: respx setup, turn 1 (non-streamed `litellm.acompletion`, streamed through Kiln's `StreamingCompletion`), turn-2 body capture, recursive JSON diff |
| `p1_openai.py`, `p1b_openai_include.py` | OpenAI chat-to-Responses bridge; `include` forwarding |
| `p2_anthropic.py`, `p2b_anthropic_fix.py` | Anthropic adaptive (Sonnet 5.5) and manual (Haiku 4.5); doubled-thinking repro and a fix prototype |
| `p3_gemini.py`, `p3b_gemini_minimal.py` | Gemini API and Vertex (auth patched) |
| `p4_openrouter.py` | OpenRouter, Claude / Gemini / OpenAI `reasoning_details` shapes |
| `p5_groq_ollama_cerebras.py` | Groq, Ollama (`openai/` + `api_base …/v1`, as Kiln routes it), Cerebras with Kiln's strip |

Method for B (input exactness): turn 1 against a fake provider gives a live `Message`. Turn 2 is
`[system, user, <assistant>, tool result or new user]`, sent three ways — (1) the live `Message`, (2)
`json.loads(json.dumps(message.model_dump(exclude_none=True)))`, (3) a dict with only `role`, `content`, `tool_calls`
and the native keys — and the captured HTTP bodies are diffed. Kiln's real kwargs were reproduced (tools,
`tool_choice=auto`, `drop_params`, `allowed_openai_params`, `cache_control_injection_points=[{message, -1}]`,
`store=False`, `reasoning_effort`, Anthropic `thinking`, OpenRouter `reasoning`/`usage`).

## The one fact that makes dict replay safe

LiteLLM turns every `Message` into `model_dump(exclude_none=True)` before any provider code runs:
`main.py:5264` (`validate_and_fix_openai_messages`) → `utils.py:8369-8384` (`convert_to_dict`). Dict messages only get
top-level `None` values removed (`utils.py:8455-8462`). So a JSON round-trip of `model_dump(exclude_none=True)` is what
the provider code sees anyway. **In every probe, for every provider, variant (2) produced a body byte-identical to
variant (1).** `model_dump(exclude_none=True)` was JSON-serialisable as-is in every case (nested `null`s survive inside
`provider_specific_fields`, e.g. `{"refusal": null}`, `{"citations": null}`; harmless).

Consequence for the design: exactness problems never come from dict-vs-`Message`. They come from (a) which keys Kiln
keeps, and (b) Kiln wanting to send something different from what LiteLLM sends for the live `Message` (strip
`reasoning_content` on Gemini, add `reasoning_details` on OpenRouter, rename for Ollama, fix doubled Anthropic text).
For (b) the in-run tool loop must get the same transform, or the saved trace stops matching the in-run request. The
simplest way to guarantee that: in `build_completion_kwargs`, convert every `Message` to the same dict Kiln saves (one
function), then apply one per-provider outbound transform to all assistant dicts, live or reloaded.

Kiln's current trace builder (`litellm_adapter.py:1174-1224`) keeps `content` as-is (`""` or `None`),
`reasoning_content`, and rebuilds `tool_calls` as `{id, type, function{name, arguments}}` (drops `index` and tool-call
`provider_specific_fields`). The probes show that rebuilt shape is enough on every provider (Gemini recovers the
tool-call signature from the id).

---

## 1. OpenAI via the chat-to-Responses bridge

Routing: LiteLLM, not Kiln, decides. `responses_api_bridge_check` (`main.py:1094-1200`, called at 5512 and 5793) bridges
`openai/` calls when a reasoning summary is requested (Kiln sends `reasoning_summary` when
`openai_reasoning_summaries` is on and the provider has `openai_reasoning_summary`, `litellm_adapter.py:820-825`), or
for gpt-5.4+ with function tools and reasoning not `none`. In `ml_model_list.py` today only `gpt-5.4-pro` and
`gpt-5.2-pro` combine tools with a summary; most gpt-5.4+/6 entries have `supports_function_calling=False` (Kiln#2003
turns them on). Probes used `openai/gpt-5.4-pro` + tools and `openai/gpt-6.1-sol` + `reasoning_summary` (no tools).

**A. Output** (`p1_openai.out`)
- Non-streamed: `message.reasoning_items = [{type, id, encrypted_content, summary:[{type,text}]}]`,
  `reasoning_content` = summary text. Built at `completion_extras/litellm_responses_transformation/transformation.py:756-790`.
  **Only the last reasoning item survives** (a later item overwrites `pending_reasoning_item`, 763-771): a reply with
  `[rs_one_part, rs_1, call]` gave `reasoning_items=[rs_1]`.
- Streamed through Kiln's `StreamingCompletion`: all items, in order (`litellm_streaming.py:83-90` re-applies them from
  the terminal chunk; plain `stream_chunk_builder` drops them).
- No `thinking_blocks`, no `provider_specific_fields`. Tool-call ids are the Responses `call_id` (`call_add`).
- `model_dump(exclude_none=True)`: `{role, content?, tool_calls, reasoning_content, reasoning_items}`; JSON-safe.

**B. Input exactness**
- (2) and (3) with `["reasoning_items"]` were IDENTICAL to (1) for tool call, narration+tool call, final answer, two
  items, streamed and not.
- The bridge emits `{"id","summary","type":"reasoning","encrypted_content"}` before the message and function calls
  (`_reasoning_input_items`, transformation.py:120-133; `_reasoning_item_to_response_input`, 333-345), for assistant
  messages with tool calls (494-495) **and** for plain final answers (531-533). So multi-turn replay works too.
- `reasoning_content` is ignored on input (dict with only `reasoning_content` → identical to no reasoning).
- `provider_specific_fields` is not read by the bridge.
- Fallback: with no `reasoning_items`, `thinking_blocks` become reasoning items **without id or encrypted content**
  (`[{'type':'reasoning','summary':[{'type':'summary_text','text':'t'}]}]`). Only matters for cross-model history,
  which the spec strips.

**C. Kiln must fix**
- **`include: ["reasoning.encrypted_content"]` is never added by LiteLLM** (turn-1 bodies have `store: false` and no
  `include`; nothing in `completion_extras/` or `llms/openai/responses/` adds it — only `llms/chatgpt/responses` does).
  The OpenAI SDK says `encrypted_content` is "populated when a response is generated with `reasoning.encrypted_content`
  in the `include` parameter" (`openai/types/responses/response_reasoning_item.py:51-55`) and that this is what makes
  reasoning usable "when the `store` parameter is set to `false`" (`response_create_params.py:71-75`). Kiln's paid probe
  set it explicitly; the paid probe also found an id-only item under `store:false` is silently dropped. So today even
  the **in-run** tool loop most likely replays id-only items that do nothing. Needs one paid confirmation.
- `include` passed as a kwarg (or in `extra_body`) **is** forwarded to `/v1/responses` — and also to
  `/v1/chat/completions` when LiteLLM does not bridge (`p1b_openai_include.out`). Whether Chat Completions rejects it is
  unverified. Safe option: add it only when the call will be bridged, e.g. by calling
  `litellm.main.responses_api_bridge_check(model, "openai", tools=…, reasoning_effort=…, reasoning_summary=…,
  api_base=…)` with the same inputs, or by Kiln's own rule (summary requested, or gpt-5.4+ with tools and effort ≠ none).
- `store: false` is already sent on both endpoints (`litellm_adapter.py:816-818`).
- Non-streamed keeps one reasoning item, streamed keeps all. Harmless today (paid probe: real replies have ≤1 item),
  but a run whose turns mix streamed and non-streamed could differ if a model ever interleaves.

Save: `reasoning_items` (verbatim). Send back: `role, content, tool_calls, reasoning_items`.

## 2. Anthropic

Kiln kwargs: Sonnet 5.5 → `reasoning_effort` + `thinking={"type":"adaptive","display":"summarized"}`
(`litellm_adapter.py:744-754`); body has `thinking` adaptive + `output_config.effort`. Haiku 4.5 →
`reasoning_effort="high"`; LiteLLM sends `thinking={"type":"enabled","budget_tokens":4096}`.

**A. Output** (`p2_anthropic.out`)
- Non-streamed: `thinking_blocks` = every block in order, `thinking` with `signature`, and `redacted_thinking` with
  `data`. `reasoning_content` = thinking texts concatenated (no separator). `provider_specific_fields` =
  `{"citations": null, "thinking_blocks": <same list>}`. Tool-call ids are `toolu_…`. Non-streamed tool calls carry
  `index` = content-block index (4); irrelevant on input.
- Streamed (via `StreamingCompletion` → `stream_chunk_builder`): `thinking_blocks` has the right blocks and signatures,
  **but every signed block's text is doubled**: `"I need to add 2 and 2.I need to add 2 and 2."`. `reasoning_content`
  is correct (single copy). `provider_specific_fields.thinking_blocks` holds only the **last** chunk's block (stale,
  e.g. only `SIG_C`) — never use it.
- Streamed tool-only replies have `content: ""` (non-streamed: absent).
- All JSON-safe.

**B. Input exactness**
- (2) and (3) with `["thinking_blocks"]` IDENTICAL to (1) for both models, streamed and not, tool and final-answer.
- Thinking blocks are prepended to the assistant content (`litellm_core_utils/prompt_templates/factory.py:2523-2526`,
  2677-2681), unsigned blocks dropped (`_drop_unsignable_thinking_blocks`, 2336-2339; `common_utils.py:1990`).
- `reasoning_content` is ignored. `provider_specific_fields.thinking_blocks` is ignored (psf-only dict → no thinking
  blocks); only `compaction_blocks`/`web_search_results` are read from psf (2515-2521, 2557-2563).
- Today's trace (no `thinking_blocks`) gives `[text, tool_use]` with `thinking` still enabled (manual model too).
- **Gotcha:** an assistant `content: ""` becomes `{"type":"text","text":"[System: Empty message content sanitised to
  satisfy protocol]"}` (`factory.py:1986-2030`, applied unconditionally at 2374). So a streamed tool-only reply is
  replayed as `[thinking, placeholder text, tool_use]`, a non-streamed one as `[thinking, tool_use]`. Live and saved
  agree as long as Kiln saves `content` unchanged (it does), so not an exactness break — but it is a deviation from what
  the model produced. Normalising `""` → `None` for assistant messages with tool calls, in both paths, would remove it.

**C. Doubled streamed thinking text — reproduced offline, root cause confirmed**
- `llms/anthropic/chat/handler.py:703-716`: on `signature_delta`, the handler emits a thinking block holding the full
  accumulated text of the current block (`self.content_blocks` resets at each `content_block_start`, 844) plus the
  signature.
- `litellm_core_utils/streaming_chunk_builder_utils.py:711-737`: `get_combined_thinking_content` appends that full text
  to the parts it already gathered from the deltas, then flushes on the signature → text twice.
- This is what the in-run streamed tool loop sends Anthropic today, under the original signature.
- Kiln-side fix: in `StreamingCompletion.__aiter__` right after `litellm.stream_chunk_builder` (`litellm_streaming.py:88`,
  beside `_apply_reasoning_items`), for Anthropic responses rebuild `message.thinking_blocks` from the chunks: each
  delta block with a `signature` is one complete block (`{type:"thinking", thinking, signature}`), each
  `redacted_thinking` delta is one block, in order. Prototype `p2b_anthropic_fix.py`: rebuilt list equals the provider's
  blocks exactly, including `display: omitted` (empty text + signature). Gate it on Anthropic (or on "a signature delta
  re-emitted text equal to the concatenated deltas") so Bedrock/Gemini streams are untouched. Because the fix sits where
  the message is built, the in-run loop and the saved trace both get the corrected blocks.
- Upstream fix would be one line in `handler.py` (emit the signature with `thinking=""`), but Kiln can't patch LiteLLM.

Save: `thinking_blocks` (top-level only; after the streamed fix). Do not save `provider_specific_fields` for Anthropic.
Send back: `role, content, tool_calls, thinking_blocks`.

## 3. Gemini API and Vertex

Probed `gemini/gemini-3.8-flash` (key) and `vertex_ai/gemini-3.8-flash` (`VertexBase._ensure_access_token_async`
patched). Both behave identically.

**A. Output** (`p3_gemini.out`)
- `reasoning_content` = the `thought:true` summary text.
- `provider_specific_fields.thought_signatures` = every `thoughtSignature` on the reply's parts, in order
  (`llms/vertex_ai/gemini/vertex_and_google_ai_studio_gemini.py:1413-1427`, stored 2326-2329). Includes text-part
  signatures, which exist **only** here.
- Function-call signature: on the tool call as `provider_specific_fields.thought_signature`
  (1567-1576) **and** embedded in the id: `call_<hex>__thought__<sig>` (1592-1595). Only the signed call gets it.
- Non-streamed also gets `thinking_blocks=[{"type":"thinking","thinking":<summary>}]` (unsigned, 1390-1411, set at
  2309-2310) and `images: []`. Streamed gets no `thinking_blocks`. Streamed text signatures that arrive on a trailing
  empty text part are captured correctly.
- JSON-safe.

**B. Input exactness**
- (2) and the dict with `provider_specific_fields, thinking_blocks, reasoning_content` IDENTICAL to (1).
- What reaches the wire for the live message: `{"thought":true,"text":<reasoning_content>}` (no signature) first
  (`llms/vertex_ai/gemini/transformation.py:883-886`), then text with `thoughtSignature = thought_signatures[0]` unless
  that signature is already on a tool call (918-945, `_collect_tool_call_thought_signatures` 640-689), then function
  calls with their signature (from tool psf or the id, `factory.py:1182-1219`; the `__thought__` suffix is removed from
  the wire id).
- When the text part is signed and the call isn't, LiteLLM puts a dummy signature
  `c2tpcF90aG91Z2h0X3NpZ25hdHVyZV92YWxpZGF0b3I=` ("skip_thought_signature_validator") on the function call. Same for
  live and dict.
- Kiln's **current** trace (no psf) loses text-part signatures: diff `.parts[1].thoughtSignature: missing`. Tool-call
  signatures survive via the id.
- Removing `reasoning_content` removes the unsigned thought part — and makes the body differ from the live `Message`.
  `p3b_gemini_minimal.out`: `{role, content, tool_calls (Kiln shape), provider_specific_fields}` equals the live
  `Message` with `reasoning_content` set to `None`, in all six cases.
- `thinking_blocks` on input: unsigned blocks are skipped; a **signed** block becomes a plain visible text part
  `{"thoughtSignature":"S","text":"t"}` (no `thought:true`, and `json.loads` of the text is spread into the part if it
  parses). Never send thinking_blocks to Gemini.
- Only `thought_signatures[0]` is ever used for text.

**C. Kiln must**
- Save `provider_specific_fields.thought_signatures` (and keep tool-call ids as today).
- Strip `reasoning_content` and `thinking_blocks` from assistant messages for `gemini_api` and `vertex` — in the
  in-run tool loop too, or turn 2 from the trace won't match the in-run request. With that, dict and live match.

Save: `provider_specific_fields: {thought_signatures}` + tool-call ids. Send back: `role, content, tool_calls,
provider_specific_fields`.

## 4. OpenRouter

**A. Output** (`p4_openrouter.out`)
- Non-streamed: `reasoning_details` is **not** a message field. It lands in
  `provider_specific_fields = {"reasoning_details": [...], "reasoning": "<text>", "refusal": null}`, because every
  unknown message key goes to psf (`litellm_core_utils/llm_response_utils/convert_dict_to_response.py:665-668`);
  `reasoning` is also copied to `reasoning_content` (`_extract_reasoning_content`, `common_utils.py:1904-1921`). The
  OpenRouter transform adds nothing (`llms/openrouter/chat/transformation.py:137-221`).
- Streamed: each chunk's `delta.reasoning_details` is present on the chunk object (probe: chunk[1] delta has it), and
  `delta.reasoning` → `reasoning_content` (transformation.py:266). `stream_chunk_builder` **drops reasoning_details
  entirely**: the built message has only `reasoning_content`.
- Tool-call ids are passed through (`tool_add_1`; Gemini's encrypted item references it by `id`).

**B. Input**
- (2)/(3) identical to (1) — but (1) itself sends `provider_specific_fields` as a top-level message key plus
  `reasoning_content`, never top-level `reasoning_details`. LiteLLM forwards every key on an input dict verbatim (the
  OpenAI-compatible base doesn't filter): a dict with `reasoning_details`, `thinking_blocks`, `reasoning_items`,
  `reasoning`, `reasoning_content` and `zzz` reached the wire with all six.
- So a top-level `reasoning_details` on a dict **is forwarded verbatim**. Fixing OpenRouter means Kiln sends something
  LiteLLM never sends for the live `Message`.
- OpenRouter docs (openrouter.ai/docs/use-cases/reasoning-tokens, fetched): on Chat Completions pass reasoning on the
  assistant message as `reasoning` (string) or `reasoning_details` (array, needed for encrypted/summarised reasoning);
  `reasoning_content` "functions identically to `reasoning`"; pass `reasoning_details` back "unmodified"; "the entire
  sequence of consecutive reasoning blocks must match the outputs … you cannot rearrange or modify". Item types:
  `reasoning.text` (`text`, `signature`), `reasoning.summary` (`summary`), `reasoning.encrypted` (`data`); common
  `id`, `format`, `index`. Streaming: "The complete reasoning sequence is built by concatenating all chunks in order";
  no merge rule for fragments of one block is given.

**C. Kiln must**
- Non-streamed: lift `provider_specific_fields.reasoning_details` to a top-level saved field.
- Streamed: accumulate `delta.reasoning_details` in `StreamingCompletion` (like `_reasoning_items_from_chunk`) and set
  it on the built message. Whether to concatenate fragments as-is (docs) or merge same-`index`/`type` fragments
  (text/summary concatenated, signature/data/id kept) is not settled by the docs — needs a paid capture comparing a
  streamed and a non-streamed reply.
- Outbound, for every assistant message on OpenRouter (live and saved): send `role, content, tool_calls,
  reasoning_details`; drop `provider_specific_fields`; drop `reasoning_content` when `reasoning_details` is present
  (else it goes as unsigned plain `reasoning`). Keep `reasoning_content` when there are no details (DeepSeek-style).

Save: `reasoning_details`. Send back: top-level `reasoning_details`, no psf, no `reasoning_content`.

## 5. Groq

**A. Output** (`p5.out`)
- Non-streamed: `ModelResponse(**response_json)` (`llms/openai_like/chat/transformation.py:114`) → `Choices` →
  `Message(**message)` (`types/utils.py:1700-1701`), so Groq's `reasoning` becomes an **extra attribute**
  `message.reasoning`; `reasoning_content` is `None`. `model_dump` has top-level `"reasoning"`. Kiln's trace builder
  reads only `reasoning_content`, so it's lost.
- Streamed: `delta.reasoning` is renamed to `reasoning_content` (`llms/groq/chat/transformation.py:357-363`).
- Fake replies need `service_tier` or Groq's `transform_response` raises (`groq/chat/transformation.py:308`).

**B. Input**
- Live non-streamed replay sends `"reasoning"`; live streamed sends `"reasoning_content"`. Dict keys `reasoning` and
  `reasoning_content` are both forwarded verbatim (Groq's `_transform_messages`, 137-160, only drops `None`s).
  (2) identical to (1).
- Which field Groq reads (or rejects) on input: **unknown** — console.groq.com isn't reachable from this session.

**C. Kiln must**
- Read `getattr(message, "reasoning", None)` when `reasoning_content` is empty, and save it as `reasoning_content`.
- Pick one outbound name for Groq (after the paid check) and apply it to live and saved messages, since live
  non-streamed and streamed already differ.

## 6. Ollama

Kiln sends Ollama through LiteLLM's `openai/` provider with `api_base = <ollama_base_url>/v1`
(`utils/litellm.py:49-52, 91-93`; `provider_tools.py:740-748`), not `ollama_chat`.

**A. Output**: non-streamed `reasoning` → `reasoning_content` plus `provider_specific_fields {reasoning, refusal:null}`;
streamed `reasoning` delta → `reasoning_content` only.

**B. Input**: an input dict's `reasoning` key **is forwarded** verbatim, and so is `reasoning_content`. Live
non-streamed replay sends `reasoning_content` + a top-level `provider_specific_fields` object; Ollama reads neither.
Ollama's `openai/openai.go` (main, fetched) declares only `Reasoning string json:"reasoning,omitempty"` on the message
and maps it to `api.Message.Thinking` (string content, array content, tool-call-only messages). No `reasoning_content`.

**C. Kiln must**: for `ollama` (and probably `docker_model_runner`, unchecked), rename `reasoning_content` →
`reasoning` and drop `provider_specific_fields` on outbound assistant messages, live and saved.

## 7. Cerebras

- LiteLLM's `CerebrasConfig` (`llms/cerebras/chat.py`) does no message filtering, so without Kiln's strip
  `reasoning_content` and psf would be sent. Kiln's `strip_assistant_fields_for_cerebras`
  (`litellm_adapter.py:82-104`, applied at 969-970) handles both `Message` objects and dicts: live and dict replays
  send `{role, tool_calls}` only, identical. Whether Cerebras still rejects the fields can't be checked offline.
- Gap: the strip list is `{reasoning_content, provider_specific_fields}`. A dict carrying `reasoning` (Groq-style
  extras, or an Ollama-style rename leaking), `thinking_blocks`, `reasoning_items` or `reasoning_details` goes through
  (`dict reasoning on wire: {..., "reasoning": "R"}`). The model-switch rule should stop native fields reaching
  Cerebras, but adding those names to the strip list is cheap insurance.

## Summary table

| Provider | Save (besides content, tool_calls with ids, reasoning_content) | Send back | Kiln fixes |
|---|---|---|---|
| OpenAI bridge | `reasoning_items` | + `reasoning_items` | add `include:["reasoning.encrypted_content"]` on bridged calls only |
| Anthropic | `thinking_blocks` (top level) | + `thinking_blocks` | rebuild streamed `thinking_blocks` after `stream_chunk_builder`; optional `""`→`None` content |
| Gemini / Vertex | `provider_specific_fields.thought_signatures` | + psf; **strip** `reasoning_content`, `thinking_blocks` (live too) | strip in both paths |
| OpenRouter | `reasoning_details` (lift from psf; accumulate when streamed) | top-level `reasoning_details`; strip psf and `reasoning_content` when present | lift, accumulate, outbound rewrite (both paths) |
| Groq | `message.reasoning` → `reasoning_content` | one chosen field (paid check) | read extra attr; normalise outbound name |
| Ollama | — | `reasoning` (rename), no psf | rename in both paths |
| Cerebras | — | nothing | keep strip; extend list |

Prior research line refs checked and correct within a line or two: `utils.py:8369-8384`, `main.py:5264`, bridge
`transformation.py:120-133, 422-549, 763-771`, `handler.py:703-715`, `streaming_chunk_builder_utils.py:715-733`,
Gemini `transformation.py:883-887`, `vertex_and_google_ai_studio_gemini.py:1590-1596`, `factory.py:1182-1220,
2523-2526, 2677-2681`, `convert_dict_to_response.py:665-669`, `openrouter/chat/transformation.py:137-160`,
`openai_like/chat/transformation.py:114`, `groq/chat/transformation.py:357-363`.

Still needs paid calls: OpenAI encrypted content without `include`, and whether Chat Completions rejects `include`;
Groq input field; OpenRouter streamed fragment merging and the exact field OpenRouter accepts per model family.
