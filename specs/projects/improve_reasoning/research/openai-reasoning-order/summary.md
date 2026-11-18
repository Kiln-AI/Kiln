# OpenAI reasoning replay order: paid probe results

- **Date:** 2026-11-18
- **Models (OpenAI direct, ids from `ml_model_list.py`):** `gpt-5.4-mini` (most runs), `gpt-5.6-luna` (cheap, and it renders earlier-turn reasoning by default), `gpt-6-astra` (flagship confirmation), `gpt-6.1-sol` (captures only).
- **SDK:** official `openai` 2.41.0, `client.responses.create` called directly. LiteLLM was not in the path; its shapes were rebuilt by hand from `transformation.py` in LiteLLM 1.105.7.
- **Settings:** `store=False`, `include=["reasoning.encrypted_content"]`, `reasoning.summary="auto"`, fixed `reasoning.effort` per experiment (medium or high), a fixed `prompt_cache_key` per experiment, 3 function tools, and a system prompt plus tools of about 4,780 tokens.
- **Script:** [probe.py](./probe.py). **Raw data:** [raw_results.json.gz](./raw_results.json.gz) (gzipped; encrypted blobs trimmed to 40 characters). `probe.py` writes `raw_results.json` uncompressed.
- **Spend:** about US$4.40, priced from LiteLLM's bundled price map. GPT-6 Astra was $3.74 of that, mini $0.47, Sol $0.14 and Luna $0.05.

## Answer in short

1. **No real reply interleaved reasoning.** In 212 captured responses across four models, every response had at most one reasoning item, and it was always the first item. No reasoning item ever came after a function call or a message. So for these replies, LiteLLM's reasoning-first rule (V2) and its last-item-only rule (V3) produced requests byte-identical to the exact replay (V1).
2. **Nothing errored because of reasoning order or position.** The "reasoning was provided without its required following item" 400 could not be reproduced. Moving reasoning items, putting two of them next to each other, putting one after its function call, ending the input on a reasoning item, or following one directly with a user message were all accepted on mini, Luna and Astra. The one 400 seen was the expected one: a `function_call_output` whose `function_call` had been removed.
3. **`id` + `encrypted_content` under `store:false` works. So does `encrypted_content` alone.** A reasoning item with an `id` and no `encrypted_content` doesn't error either. It is silently dropped, and the token count falls to the no-reasoning level.
4. **Dropping `phase` changed nothing measurable.** The prompt the server builds is token-for-token the same with or without `phase`, and with or without message and call ids (LiteLLM's shape). A request without `phase` got a full cache hit from a primed request that had it. Answers were the same. In this data every commentary message was followed by a function call, so the server could infer the phase. A reply that ends on a commentary message was not tested.
5. **The cache cost comes from inconsistency, not from order.** On Luna and Astra, the next call reused the whole earlier prefix when it was sent in the same shape as the call that wrote the cache. That held for every shape, including the synthetic reorders. When the shape changed anywhere in the history, the hit fell back to the system prompt and tools alone (about 4,800 tokens). It never stopped partway through the history.
   - **Kiln today:** the tool loop runs with reasoning, then the next turn is sent from the saved trace with no reasoning. That loses the whole turn-1 history from the cache: 808 of 5,583 tokens on Luna, 2,115 of 6,920 on Astra.
   - **Exact order to LiteLLM shape:** going from the exact shape to LiteLLM's shape (no `phase`, no item ids) kept the full hit. The server renders them identically.
   - **Exact order to reordered reasoning:** going from the exact shape to a synthetic reorder (round 2's reasoning moved into round 1) also fell back to the system prompt.
6. **Whether earlier-turn reasoning counts depends on the model.** GPT-5.4 mini drops reasoning from earlier turns by default (`reasoning.context` defaults to `current_turn`). Its turn-2 input tokens were the same with and without reasoning (5,546 vs 5,548), so no replay shape can keep its turn-1 tool-loop prefix cached. Luna and Astra render earlier-turn reasoning by default: +247 tokens on Luna, +868 on Astra. Mini with `reasoning.context="all_turns"` renders it too (+231). OpenAI's own page names only GPT-5.6 and GPT-6.1 Sol as defaulting to all turns, but GPT-6 Astra behaved the same way. That matches Azure's docs.
7. **Behaviour and reasoning tokens didn't change in any visible way.** Every answer in every variant, across all three models, was correct: it repeated the right quote ids and weights. Reasoning tokens on the next call were small (0-170) and noisy, with no pattern by variant. Within a turn, every variant made the same next tool call.

**What this means for the design.** Reordering or keeping only the last reasoning item is harmless today because real replies don't interleave. Nothing errors either way. What matters is that the tool loop and the next turn send history in the same shape, with reasoning included. If Kiln replays reasoning from the saved trace in the same shape LiteLLM used during the loop, the cache hits fully on models that render earlier-turn reasoning. Exact order isn't needed for that. If a future model does interleave, the streamed path (all items, moved first) and the non-streamed path (last item only) would produce different histories. A run whose loop and resume go through different paths would then miss the cache.

## Interleaving frequency

| Capture | Model | Effort | Tasks | Responses | With reasoning | More than 1 reasoning item | Reasoning after a call or message | Messages | Messages with `phase` | Parallel calls |
|---|---|---|---|---|---|---|---|---|---|---|
| default tasks | gpt-5.4-mini | medium | 10 | 47 | 44 | 0 | 0 | 47 | 47 | 2 |
| hard, with preamble | gpt-5.4-mini | high | 5 | 20 | 20 | 0 | 0 | 20 | 20 | 14 |
| hard, no preamble | gpt-5.4-mini | high | 5 | 20 | 20 | 0 | 0 | 5 | 5 | 14 |
| default tasks | gpt-5.6-luna | high | 4 | 20 | 19 | 0 | 0 | 20 | 20 | 0 |
| default tasks | gpt-6-astra | medium | 10 | 45 | 1 | 0 | 0 | 45 | 45 | 2 |
| hard, with preamble | gpt-6-astra | high | 5 | 20 | 18 | 0 | 0 | 20 | 20 | 14 |
| default tasks | gpt-6.1-sol | high | 4 | 20 | 6 | 0 | 0 | 20 | 20 | 0 |
| hard, no preamble | gpt-6.1-sol | high | 5 | 20 | 9 | 0 | 0 | 5 | 5 | 14 |
| **Total** | | | | **212** | **157** | **0** | **0** | **182** | **182 (100%)** | **60** |

- The shape was always `[reasoning?, message(commentary)?, function_call...]` or `[reasoning?, message(final_answer)]`. Parallel calls came as several `function_call` items after the single reasoning item, never with reasoning between them. Responses with `parallel_tool_calls` true and false looked the same.
- Every assistant message carried `phase`: `commentary` before tool calls, `final_answer` at the end. No response had more than one message.
- "Default tasks" ask for one or two orders and 3-7 tool rounds, with a system-prompt rule to say one sentence before each tool call. "Hard" tasks ask for 6 orders, 12 quotes and arithmetic, and use up to 3,300 reasoning tokens on the final answer.

## Variants

The turn-1 history is the user message, then each response's output items, then that response's `function_call_output` items.

- **V1** sends every output item exactly as returned, including `phase`, `status` and ids.
- **V2** moves all reasoning first in each response.
- **V3** keeps only the last reasoning item, moved first.
- **V4** is V1 without `phase`.
- **V5** has no reasoning items.
- **V6** sends reasoning without `id`.
- **V7** is what LiteLLM's bridge sends for a streamed reply. Reasoning comes first with `id`, `encrypted_content` and `summary`. Then comes one assistant message with no id or `phase`, then function calls with no id.
- **V8** is the non-streamed version of V7, with only the last reasoning item.
- **V9** is V7 without reasoning. It's what Kiln sends today from a saved trace.
- **V10** is reasoning with an `id` but no `encrypted_content`.
- **S1** and **S2** are synthetic, because no real reply interleaved. S1 moves round 2's reasoning item into round 1, right after round 1's own reasoning. That gives `[A, B, message, call, output, message, call, output]`, the shape V2 produces for an interleaved `[A, call 1, B, call 2]`. S2 moves round 1's reasoning after its function call.

**Measurement.**

- For each variant, a "prime" call sends the turn-1 history up to the last tool output: the input of turn 1's final tool round. It uses `max_output_tokens=16` and writes the cache.
- Then the turn-2 request (turn 1 plus the final answer plus a new user message) is sent once. That call measures how much of turn 1 is reused. It is then sent 2-3 more times, which measures how well an identical request caches.
- Each variant's first user message got a unique tag, so one variant couldn't warm the cache for another. That changes input tokens by a few tokens between variants. Differences under about 10 tokens are only the tag.
- The turn-2 question asks the model to repeat the quote ids, weights and tier discounts without calling tools. Correct means it named every quote id.

### Across turns: GPT-5.4 mini (medium, 7 tool rounds; earlier-turn reasoning not rendered by default)

| Variant | Status | Turn-1 prefix | Turn-2 input | Cached, first turn-2 call | Cached, repeats (median) | Reasoning tokens (median) | n | Correct |
|---|---|---|---|---|---|---|---|---|
| V1 exact | 200 | 5,510 | 5,546 | 4,608 | 5,120 | 38 | 4 | 4/4 |
| V2, V3 | same request as V1 | | | | | | | |
| V4 no phase | 200 | 5,511 | 5,547 | 4,224 | 5,376 | 37 | 4 | 4/4 |
| V5 no reasoning | 200 | 5,349 | 5,548 | 5,248 | 5,376 | 40 | 4 | 4/4 |
| V6 no reasoning id | 200 | 5,513 | 5,549 | 4,608 | 5,120 | 85 | 4 | 4/4 |
| V7 LiteLLM streamed | 200 | 5,516 | 5,552 | 4,608 | 5,120 | 49 | 4 | 4/4 |
| V8 | same request as V7 | | | | | | | |
| V9 LiteLLM, no reasoning | 200 | 5,354 | 5,553 | 5,120 | 5,120 | 67 | 4 | 4/4 |
| V10 id only | 200 | 5,350 | 5,549 | 5,248 | 5,376 | 48 | 4 | 4/4 |
| S1 hoisted reasoning | 200 | 5,516 | 5,552 | 4,608 | 5,120 | 31 | 4 | 4/4 |
| S2 reasoning after call | 200 | 5,513 | 5,549 | 4,608 | 5,120 | 81 | 4 | 4/4 |

Mini reports cached tokens in coarse steps (4,224 / 4,608 / 5,120 / 5,376) and often missed a prefix that had just been written. Its cache numbers only show that nothing broke badly. With `reasoning.context="all_turns"`, mini's turn-2 input rose to 5,781 with reasoning against 5,550 without, so mini does honour the setting.

### Across turns: GPT-5.6 Luna (high, 7 tool rounds; earlier-turn reasoning rendered by default)

| Variant | Status | Turn-1 prefix | Turn-2 input | Cached, first turn-2 call | Cached, repeats (median) | Reasoning tokens (median) | n | Correct |
|---|---|---|---|---|---|---|---|---|
| V1 exact | 200 | 5,578 | 5,871 | 5,575 | 5,868 | 42 | 4 | 4/4 |
| V2, V3 | same request as V1 | | | | | | | |
| V4 no phase | 200 | 5,579 | 5,872 | 5,576 | 5,869 | 60 | 4 | 4/4 |
| V5 no reasoning | 200 | 5,422 | 5,624 | 5,419 | 5,621 | 31 | 4 | 4/4 |
| V6 no reasoning id | 200 | 5,581 | 5,874 | 5,578 | 5,871 | 60 | 4 | 4/4 |
| V7 LiteLLM streamed | 200 | 5,584 | 5,877 | 5,581 | 5,874 | 30 | 4 | 4/4 |
| V8 | same request as V7 | | | | | | | |
| V9 LiteLLM, no reasoning | 200 | 5,427 | 5,629 | 5,424 | 5,626 | 49 | 4 | 4/4 |
| V10 id only | 200 | 5,423 | 5,625 | 5,420 | 5,622 | 0 | 4 | 4/4 |
| S1 hoisted reasoning | 200 | 5,584 | 5,877 | 5,581 | 5,874 | 49 | 4 | 4/4 |
| S2 reasoning after call | 200 | 5,581 | 5,874 | 5,578 | 5,871 | 47 | 4 | 4/4 |

### Across turns: GPT-6 Astra (high, 4 tool rounds with 6 parallel lookups; flagship confirmation)

| Variant | Status | Turn-1 prefix | Turn-2 input | Cached, first turn-2 call | Cached, repeats (median) | Reasoning tokens (median) | n | Correct |
|---|---|---|---|---|---|---|---|---|
| V1 exact | 200 | 6,912 | 8,442 | 6,909 | 8,439 | 101 | 3 | 3/3 |
| V2, V3 | same request as V1 | | | | | | | |
| V4 no phase | 200 | 6,913 | 8,443 | 6,910 | 8,440 | 129 | 3 | 3/3 |
| V5 no reasoning | 200 | 6,562 | 7,574 | 6,559 | 7,571 | 116 | 3 | 3/3 |
| V6 no reasoning id | 200 | 6,915 | 8,445 | 6,912 | 8,442 | 138 | 3 | 3/3 |
| V7 LiteLLM streamed | 200 | 6,918 | 8,448 | 6,915 | 8,445 | 117 | 3 | 3/3 |
| V8 | same request as V7 | | | | | | | |
| V9 LiteLLM, no reasoning | 200 | 6,567 | 7,579 | 6,564 | 7,576 | 120 | 3 | 3/3 |
| V10 id only | 200 | 6,563 | 7,575 | 6,560 | 7,572 | 133 | 3 | 3/3 |
| S1 hoisted reasoning | 200 | 6,918 | 8,448 | 6,915 | 8,445 | 113 | 3 | 3/3 |
| S2 reasoning after call | 200 | 6,915 | 8,445 | 6,912 | 8,442 | 110 | 3 | 3/3 |

### Cache written in one shape, next turn sent in another (n=1 each)

| Turn 1's last tool round sent as | Turn 2 sent as | Luna: cached / turn-1 prefix | Astra: cached / turn-1 prefix |
|---|---|---|---|
| V7 LiteLLM streamed | V9 no reasoning (Kiln today) | 4,775 / 5,583 | 4,805 / 6,920 |
| V1 exact | V5 no reasoning | 4,775 / 5,583 | 4,805 / 6,920 |
| V1 exact | S1 hoisted reasoning | 4,775 / 5,583 | 4,805 / 6,920 |
| V1 exact | V7 LiteLLM streamed | 5,580 / 5,583 | 6,917 / 6,920 |

The 4,775 and 4,805 figures are the system prompt and tools alone. On mini, both pairs run (V7 to V9 and V1 to V7) cached 4,608, the same as an exact replay. Mini drops earlier-turn reasoning at turn 2, so the turn-2 prompt never matches what turn 1's loop cached.

`phase` check (`probe.py phase`): the exact turn-2 request was primed, then sent again under the same cache key without `phase`, in the LiteLLM shape, and exactly.

| Turn 2 sent as | Luna: input / cached | Astra: input / cached |
|---|---|---|
| V4, no `phase` | 5,869 / 5,866 | 8,442 / 8,439 |
| V7, LiteLLM shape | 5,868 / 5,865 | 8,440 / 8,437 |
| V1, exact | 5,868 / 5,865 | 8,440 / 8,437 |

Each sent request had the same token count as its primed request and was fully cached. So `phase` and the item ids don't change the prompt the server builds in this conversation.

### Within one turn (replay rounds 1-3, measure the round-4 call)

| Variant | Mini: status, input, cached (repeats), reasoning | Luna: status, input, cached (first / repeats), reasoning |
|---|---|---|
| V1 exact | 200, 5,200, 5,120, 9 | 200, 5,189, 5,083 / 5,186, 6 |
| V2, V3 | same request as V1 | same request as V1 |
| V4 no phase | 200, 5,201, 5,120, 9 | 200, 5,190, 5,084 / 5,187, 0 |
| V5 no reasoning | 200, 5,082, 4,608, 0 | 200, 5,112, 5,025 / 5,109, 0 |
| V7 LiteLLM streamed | 200, 5,206, 5,120, 9 | 200, 5,195, 5,089 / 5,192, 8 |
| S1 hoisted reasoning | 200, 5,206, 5,120, 9 | 200, 5,195, 5,089 / 5,192, 0 |
| S2 reasoning after call | 200, 5,203, 5,120, 9 | 200, 5,192, 5,086 / 5,189, 0 |

Every variant made the same next tool call: `lookup_order` for the second order on mini, `lookup_customer` on Luna. Within a turn, reasoning is rendered on both models: +118 tokens on mini and +77 on Luna with reasoning against without. Each shape cached fully against a prime written in the same shape.

### Reasoning items without their following item (`probe.py orphan`, mini and Luna)

| Input | Result |
|---|---|
| user, reasoning, user ("Please continue.") | 200 |
| user, reasoning (last item) | 200 |
| user, reasoning, function call, output (commentary message removed) | 200 |
| user, reasoning, output (function call removed) | 400 "No tool call found for function call output with call_id …" (about the call, not the reasoning) |

## Caveats

- **Sample size.** Each cell is 3-4 calls at most, and each cross-shape pair is a single call. The reasoning-token medians are tiny and swing widely between identical requests (for example 0, 0, 61). They can't show small behaviour effects, only that nothing broke.
- **Narrow workload.** It's one synthetic support-agent workload with three simple tools. Interleaving could still appear in other workloads: long coding agents, hosted tools, or `xhigh`/`max` effort. It was never seen, so V2 and V3 were only tested through the synthetic S1 and S2 shapes. Those shapes use real reasoning items from different responses, not items from one interleaved response.
- **`phase` only tested where it can be inferred.** It was only checked in conversations where every commentary message was followed by a function call. A reply that ends on a commentary message, which is the "preamble treated as final answer" case OpenAI warns about, wasn't tested.
- **Caching is best-effort.**
  - Mini's cached counts are coarse and often lag a freshly written prefix.
  - Luna and Astra were exact: cached tokens equal the earlier request's input minus 3. They hit either the whole earlier request or the system-prompt checkpoint, never part of the history.
  - Two prime calls on mini came back `incomplete` with zero usage (marked "usage missing" in the raw data). The calls after them behaved normally.
  - One call returned a transient 500. It succeeded on retry with a different `prompt_cache_key` (the first key contained spaces and brackets).
- **Default `reasoning.context` wasn't set explicitly** except in the one mini `all_turns` run. The models' defaults may change.
- **Small token differences between rows are the per-variant tag** in the first user message, not the variant.
