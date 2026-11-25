# Current state with the pinned LiteLLM (1.102.0)

Question: for each OpenAI-direct provider that has `supports_function_calling=False`, which endpoint does a tools-plus-reasoning request hit today, and what would break if the flag were removed?

## Method

- `OPENAI_API_KEY` is not set in this environment, and no paid call was made.
- **Static check.** A script calls LiteLLM's `responses_api_bridge_check` directly for every model id, tool shape and effort. It was run once with LiteLLM's bundled model map (`LITELLM_LOCAL_MODEL_COST_MAP=True`) and once with the live map that LiteLLM downloads at import time from `raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`, which is LiteLLM's default. The routing results are identical. Script: `/tmp/claude-0/-home-user-Kiln/dd147251-f363-5e17-95c4-80813a10f3ed/scratchpad/model_map_probe.py`. Outputs: `probe_local.txt`, `probe_remote.txt` in the same folder.
- **End-to-end check.** A local fake OpenAI server on 127.0.0.1 records every request body. It serves `/v1/chat/completions` and `/v1/responses`. It returns a `function_call` on the first turn and a final message after a `function_call_output`. The driver runs **Kiln's real adapter** (`adapter_for_task` → `LiteLlmAdapter.invoke`) with the built-in `add` tool and the tool task from `test_litellm_adapter_tools.build_test_task`. `OPENAI_BASE_URL` points at the fake and the key is fake. Kiln sets no `api_base` for the OpenAI provider, and both LiteLLM paths fall back to `OPENAI_BASE_URL` (`_resolve_openai_api_base` in `main.py`; `get_complete_url` in `llms/openai/responses/transformation.py`). Scripts: `fake_openai_server.py`, `drive_kiln_against_fake.py`, `dump_bodies.py`, `structured_probe.py`, `temperature_probe.py` in the same scratchpad folder. Outputs: `fake_run_output.txt`, `dump_bodies_output.txt`, `structured_probe_output.txt`, `temperature_probe_output.txt`.
- The flag only feeds the UI (`app/desktop/studio_server/provider_api.py` → `available_models_dropdown.svelte`). The adapter never reads it, so calling the adapter with tools shows exactly what removing the flag would allow.
- Caveats. The fake always returns a reasoning summary, so "reasoning surfaced" in the fake runs is an artifact; real OpenAI returns none unless a summary is requested (#1757 commit `ca276a72`). The fake's 400 rule on `/v1/chat/completions` imitates OpenAI's error but is not a captured response. Because the fake's host is not `api.openai.com`, LiteLLM's "unset effort" branch cannot fire. That does not matter for Kiln, which always sends an explicit `reasoning_effort` for these providers.

## Routing decision per model id (LiteLLM 1.102.0)

`R` = bridged to `/v1/responses`, `C` = stays on `/v1/chat/completions`. Request has one function tool, OpenAI default base URL.

```
                       effort:
gpt-5.4                none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.5                none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.6-sol            none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.6-terra          none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.6-luna           none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-6-astra            none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-6-sol              none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-6-luna             none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-6.1-sol            none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-6.1-terra          none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.4-pro            none:R minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.2-pro            none:R minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.4-mini           none:C minimal:R low:R medium:R high:R xhigh:R max:R None:R
gpt-5.2                none:C minimal:C low:C medium:C high:C xhigh:C max:C None:C
gpt-5                  none:C minimal:C low:C medium:C high:C xhigh:C max:C None:C
```

Without tools (effort `high`), all ten affected ids stay on `C`. Only `gpt-5.4-pro` and `gpt-5.2-pro` go to `R`, because the model map marks them `mode: responses`.

Model-map facts that matter (bundled vs live map): `gpt-6-sol`, `gpt-6-luna`, `gpt-6.1-sol`, `gpt-6.1-terra` are **missing from the bundled 1.102.0 map** and present in the live map. Routing does not depend on this, because the rule is name-based. Two things do depend on it: whether `top_p` and temperature are kept or dropped (see [other-chat-completions-workarounds.md](./other-chat-completions-workarounds.md)), and cost. With the bundled map, the fake runs report `usage.cost: 0.0` for those four ids.

## Per affected provider: what a run with tools would do today

The default thinking level decides the endpoint, so one model can use **both** endpoints depending on the level the user picks.

| Provider | Levels offered (OpenAI direct) | Default | Tools at default level → | Tools at a non-`none` level → |
|---|---|---|---|---|
| `gpt-5.4` | none, low, medium, high, xhigh | none | chat completions | responses |
| `gpt-5.5` | none, low, medium, high, xhigh | none | chat completions | responses |
| `gpt-5.6-sol` | none, low, medium, high, xhigh | none | chat completions | responses |
| `gpt-5.6-terra` | none, low, medium, high, xhigh | medium | responses | responses |
| `gpt-5.6-luna` | none, low, medium, high, xhigh | none | chat completions | responses |
| `gpt-6-astra` | low, medium, high, xhigh, max | medium | responses | responses |
| `gpt-6-sol` | none, low, medium, high, xhigh, max | medium | responses | responses |
| `gpt-6-luna` | none, low, medium, high, xhigh, max | medium | responses | responses |
| `gpt-6.1-sol` | low, medium, high, xhigh | medium | responses | responses |
| `gpt-6.1-terra` | none, low, medium, high, xhigh | medium | responses | responses |

## What the fake-server runs showed (Kiln adapter, LiteLLM 1.102.0)

**A. Tools + `thinking_level="high"`: every affected id goes to `/v1/responses`, and the tool loop completes.** Example (`gpt-5.5`):

```
req1: /v1/responses {"model": "gpt-5.5", "reasoning": {"effort": "high"}, "temperature": 1.0, "tool_choice": "auto", "n_tools": 1, "tool0_keys": ["description", "name", "parameters", "strict", "type"], "tool0_strict": false, "input_item_types": ["message"]}
req2: /v1/responses {"model": "gpt-5.5", "reasoning": {"effort": "high"}, "temperature": 1.0, "tool_choice": "auto", "n_tools": 1, ..., "input_item_types": ["message", "reasoning", "function_call", "function_call_output"]}
tool called with: [{'a': 2, 'b': 2}]
final output: 'The answer is [4]'
```

All ten ids produced the same shape. The full bodies show:
- Function tools are sent with `"strict": false` explicitly.
- No `store` key is sent, so OpenAI's default applies. The migration guide says "Responses are stored by default."
- No `include` key is sent, so no `reasoning.encrypted_content` is requested.
- No `reasoning.summary` is sent.
- `temperature: 1.0` is sent. `top_p` is dropped.
- On the second turn the reasoning item is replayed **by id only**: `{"id": "rs_fake_1", "summary": [...], "type": "reasoning"}`.

Inference, to be confirmed by the OpenAI subtopic: replay by id depends on OpenAI having stored the first response, which holds only while `store` is left at its default.

**B. Tools + `thinking_level="none"`: stays on `/v1/chat/completions`** with `reasoning_effort: "none"` and the normal chat tool shape. This holds for `gpt-5.4`, `gpt-5.5`, `gpt-5.6-*`, `gpt-6-sol`, `gpt-6-luna` and `gpt-6.1-terra`. Whether OpenAI accepts this today is the open question noted in [openai-error-messages.md](./openai-error-messages.md); current OpenAI docs say it does.

**C. A reply with narration and a function call in one turn: the tool call is silently lost.**

```
--- gpt-6.1-sol thinking_level=high
  req1: /v1/responses {...}
  tool called with: []
  final output: 'Let me add those numbers.'
  error: None
```

Only one request is made. The tool never runs, and the narration is saved as the final answer with no error. This matches #1757's paid finding on LiteLLM 1.87.1 ("two choices came back, the tool never ran, and the output was the narration only"). It still happens on 1.102.0.

**D. Structured output + tools: `text.format.strict` is `false` on the wire.**

```
gpt_5_5: /v1/responses text.format={"type": "json_schema", "name": "task_response", "strict": false} response_format=False
gpt_6_astra: /v1/responses text.format={"type": "json_schema", "name": "task_response", "strict": false} response_format=False
```

This matches #1757's finding ("the litellm bridge turns the absent key into `strict: false`, while `/v1/responses` defaults to true"). It still happens on 1.102.0.

**E. Custom sampling parameters are silently dropped.** With `temperature=0, top_p=0.5` and effort `high`, neither key appears on the bridged request, and no error is raised. See [other-chat-completions-workarounds.md](./other-chat-completions-workarounds.md) for the chat path.

**F. Tool-less runs stay on Chat Completions, including `max`.**

```
gpt_6_1_sol level=max: /v1/chat/completions {"model": "gpt-6.1-sol", "reasoning_effort": "max", ...}
gpt_6_1_terra level=max: /v1/chat/completions {"model": "gpt-6.1-terra", "reasoning_effort": "max", ...}
gpt_5_4_pro level=high: /v1/responses {"model": "gpt-5.4-pro", "reasoning": {"effort": "high"}, ...}
```

Kiln's adapter does not check the level against `available_thinking_levels`; the UI does that. Per #1830, #1831 and #1982, OpenAI answers `max` on chat with a 400.

## What would break if the flag were removed today

On `main` (LiteLLM 1.102.0), measured with the fake server unless marked otherwise:

1. **Nothing returns the original 400 at non-`none` levels.** LiteLLM bridges every affected id. The workaround no longer protects against the error it was added for.
2. **Silent wrong answers.** A turn with text plus a tool call loses the call (C). This is the most serious defect: it produces no error.
3. **Unconstrained structured output on the bridged path.** `strict: false` (D). #1757 saw small models return strings instead of objects because of this (paid, on 1.87.1).
4. **No reasoning text** on bridged calls, because Kiln does not request a summary (#1757 commit `ca276a72`: "OpenAI's /v1/responses returns no reasoning at all unless the request asks for a summary"). Not measurable with the fake.
5. **Storage and retention.** No `store` is sent, so responses are stored by OpenAI's default, and reasoning items are replayed by id. Kiln already does this today for `gpt-5.4-pro` and `gpt-5.2-pro` (#1757: "litellm already routes GPT-5.4 Pro this way today").
6. **The endpoint depends on the level.** `"none"` goes to chat and other levels go to responses, so traces, reasoning and parameter handling differ by thinking level within one model (table above). Whether OpenAI accepts `"none"` plus tools on gpt-5.4 / gpt-5.5 today is unverified (#1351 saw it rejected in April 2026).
7. **Older clients.** The remote model list replaces the built-in list on every client. Releases v1.0.3 – v1.2.0 lock LiteLLM 1.87.1, which bridges gpt-5.4 / 5.5 / 5.6-* (including at `"none"`) but **not** `gpt-6-*`. Removing the flag from the remote list would give those clients the original chat 400 for GPT-6 Astra, Sol, Luna, 6.1 Sol and 6.1 Terra. #1757 also reported that 1.87.1's `drop_params` removed `reasoning_effort` for `gpt-6-astra`. Releases up to v1.0.2 (LiteLLM 1.81.16) would get the 400 for every affected id at non-`none` levels.
8. **Not tested here:** streaming (`invoke_openai_stream`, `invoke_ai_sdk_stream`, the chat UI) through the bridge, and multi-turn `prior_trace` replay of bridged turns. Both belong to the LiteLLM and adapter subtopics.
