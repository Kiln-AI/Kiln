# How `reasoning_effort` on `completion()` is translated, dropped or rejected (litellm 1.102.0)

Scope: what LiteLLM does to `reasoning_effort` before anything reaches OpenAI, Azure or OpenRouter. Whether OpenAI itself accepts a given value is out of scope here (subtopics 1 and 4). Kiln calls `completion()` with `drop_params=True` (`libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py:747`), so the silent-drop branches below are the ones Kiln hits.

## Which config handles the param

- `openai/gpt-5*`, `gpt-6*` (except `gpt-5-chat*` and `*search*`) → `OpenAIGPT5Config` (`llms/openai/chat/gpt_5_transformation.py`).
- `openai/o1|o3|o4*` → `OpenAIOSeriesConfig`. `reasoning_effort` is supported and passed through unchanged. Tools are dropped only if the cost map says the model lacks function calling.
- Unknown `openai/*` names → `OpenAIUnknownModelConfig`. It forwards `reasoning_effort` ("let the server decide").
- `azure/gpt-5*` → `AzureOpenAIGPT5Config`. It extends the OpenAI rules and adds a `none` guard.
- `openrouter/*` → `OpenrouterConfig`. `reasoning_effort` is allowed when `supports_reasoning` is true for the model, and `max` is rewritten to `xhigh`. The param is sent **top-level as `reasoning_effort`** (probe K body: `"reasoning_effort": "high", "usage": {"include": true}`). LiteLLM does not convert it into OpenRouter's `reasoning: {effort}` object on this path. Whether OpenRouter honours the top-level form belongs to subtopic 4.

## OpenAI GPT-5 family rules on the chat path (verbatim logic, summarised)

From `OpenAIGPT5Config.map_openai_params`:

1. **A dict effort is flattened.** `{"effort": "high", "summary": "detailed"}` becomes `"high"`, because "The chat completion API expects an effort string". The summary is lost on chat, unless the summary alias triggers the bridge (see the bridge doc).
2. **`xhigh` is opt-in.** It is kept only if the cost map has `supports_xhigh_reasoning_effort: true`. Otherwise it is **dropped when `drop_params`**, else `UnsupportedParamsError("reasoning_effort=xhigh is not supported for this model.")`.
3. **`minimal` / `low` are opt-out.** They are dropped or rejected only when the map *explicitly* sets `supports_{level}_reasoning_effort: false`. The code comment reads: "Example: gpt-5.5-pro only accepts {medium, high, xhigh}, so it sets supports_low_reasoning_effort=false (and supports_minimal=false)."
4. **`none` is never checked on the OpenAI path.** `gpt-5` + `reasoning_effort="none"` was forwarded as is (probe Y). Open issue [#40472](https://github.com/BerriAI/litellm/issues/40472): "supports_none_reasoning_effort is never enforced, so gpt-5 / gpt-5-mini forward reasoning_effort=none into a predictable provider 400". The **Azure** config does check it. It drops `none` when `drop_params` is set, and otherwise raises with a link to [#16704](https://github.com/BerriAI/litellm/issues/16704).
5. **Sampling params.** `temperature != 1` is allowed only when the effort "resolves to `none`": either set explicitly, or the map's `default_reasoning_effort` is `none`. Otherwise it is dropped or rejected. `logprobs`, `top_logprobs` and `top_p` follow the same gate on models that support `none`.
6. `max_tokens` → `max_completion_tokens`.
7. **No tool-related drop.** Since the gpt-5.4+ auto-route was added, nothing in 1.102.0 removes `reasoning_effort` because tools are present. The request goes to `/v1/responses` instead (see [completion-to-responses-bridge.md](./completion-to-responses-bridge.md)). The OpenAI provider docs page still describes the older "drops `reasoning_effort`" behaviour. That page is stale.

These parameter-mapping rules also run **before** the bridge, so the same drops happen on `openai/responses/...` and on auto-bridged requests.

### Probe results (wire captures, `drop_params=True`, bundled cost map)

| Request | Path | `reasoning` on the wire |
|---|---|---|
| `openai/gpt-5.5`, `high` | `/v1/chat/completions` | `reasoning_effort: "high"` |
| `openai/gpt-5.5`, `xhigh` | chat | `reasoning_effort: "xhigh"` |
| `openai/gpt-5`, `xhigh` | chat | **missing (silently dropped)** |
| `openai/gpt-5.5`, `minimal` | chat | **missing (silently dropped)**: map has `supports_minimal_reasoning_effort: false` |
| `openai/responses/gpt-5.5`, `minimal` | `/v1/responses` | **missing** |
| `openai/responses/gpt-5`, `xhigh` | `/v1/responses` | **missing** |
| `openai/gpt-5.5-pro`, `low` (auto-bridged) | `/v1/responses` | **missing**: map has `supports_low_reasoning_effort: false` |
| `openai/gpt-5`, `none` | chat | `reasoning_effort: "none"` (forwarded unvalidated) |
| `openai/gpt-5.5`, `none` + tools | chat | `reasoning_effort: "none"` + tools (stays on chat) |
| `openai/gpt-5.5`, `high` + tools | `/v1/responses` | `reasoning: {effort: "high"}` |
| `openrouter/openai/gpt-5.5`, `high` + tools | OpenRouter chat | top-level `reasoning_effort: "high"` |

**What this means for the "can't set thinking level" claim** (inference, handed to subtopic 4). When a level is silently dropped, LiteLLM sends no effort at all, so the provider uses its default and the caller sees no error. Whether that is right depends on whether the cost map's capability flags are accurate. Two places where the sources disagree:

- The LiteLLM OpenAI docs table lists `gpt-5.5` as supporting "none, minimal, low, medium, high, xhigh". The bundled 1.102.0 map sets `supports_minimal_reasoning_effort: false` for `gpt-5.5`. One of them is wrong. Settling it needs OpenAI's own model page (subtopic 1).
- The bundled map declares `default_reasoning_effort: "none"` for `gpt-5.2`, `gpt-5.4` and `gpt-5.4-mini`. The bridge gate's comment says "unset reasoning_effort means medium server-side" for gpt-5.4+, and it bridges tools-without-effort requests on that basis. The two code paths assume different defaults for the same model.

### Reasoning flags in the bundled 1.102.0 map (relevant OpenAI models)

| model | none | minimal | low | xhigh | default declared |
|---|---|---|---|---|---|
| gpt-5 | false | true | (unset → allowed) | false | – |
| gpt-5-pro | false | true | – | false | – |
| gpt-5.2 | true | false | – | true | `none` |
| gpt-5.4 | true | false | – | true | `none` |
| gpt-5.4-mini | true | false | – | true | `none` |
| gpt-5.5 | true | false | – | true | – |
| gpt-5.5-pro | false | false | false | true | – |
| o3 | (only `supports_reasoning`) | | | | |

Because LiteLLM loads the cost map from a remote URL at import by default (see the bridge doc), these flags can change at runtime without a package upgrade.

## Related open issues

- [#43910](https://github.com/BerriAI/litellm/issues/43910) (open, 2026-09-30). "GPT-6.1 Sol forwards unsupported none/minimal reasoning effort on Chat Completions and Responses".
- [#40472](https://github.com/BerriAI/litellm/issues/40472) (open). `none` is not enforced for gpt-5/gpt-5-mini.
- [#43708](https://github.com/BerriAI/litellm/issues/43708) (open). Databricks-hosted gpt-5.6 family: "Function tools fail with reasoning_effort error ... on /chat/completions". The auto-route gate only covers `openai`/`azure`, plus `azure_ai` from 1.104.
- [#40123](https://github.com/BerriAI/litellm/issues/40123) (open, reported on v1.98.0). `gpt-6-astra` tool calls were rejected on chat and "the Responses bridge never engages". In 1.102.0 `is_model_gpt_5_4_plus_model("gpt-6-astra")` returns True, and my direct check routed it to `responses`. So this looks fixed in code for `openai/` at 1.102.0, although the issue is still open.
- Release notes, 1.103.0: "Accept and forward verbosity on gpt-5.x chat completions - PR #41509", "Flatten dict-form reasoning_effort to its effort string - PR #41335", "Translate the reasoning object into a chat-completion reasoning effort - PR #36363" ([v1.103.0 notes](https://docs.litellm.ai/release_notes/v1.103.0/v1-103-0)). 1.104.0: "Keep reasoning_effort a string for targets that stay on chat completions - PR #42401", "Honour global api_base ... and reject non-string reasoning_effort with 400 - PR #42512" ([v1.104.0 notes](https://docs.litellm.ai/release_notes/v1.104.0/v1-104-0)).
