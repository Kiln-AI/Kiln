# Per-model endpoint and reasoning-effort matrix (OpenAI direct API)

Sources: OpenAI model pages, read as Markdown (`https://developers.openai.com/api/docs/models/<id>.md`) on 2026-10-05, plus the [latest-model guide](https://developers.openai.com/api/docs/guides/latest-model) and the [deprecations page](https://developers.openai.com/api/docs/deprecations.md). Each "Endpoints" table on a model page has a `Support` column of "Supported" / "Not supported". That column is the source for the CC and Resp columns below.

The rows are the OpenAI reasoning models that appear in Kiln's `ml_model_list.py`, plus a few close relatives. This covers only OpenAI's own API. Azure, OpenRouter and other hosts belong to other subtopics.

Abbreviations: CC = Chat Completions (`/v1/chat/completions`), Resp = Responses (`/v1/responses`).

| Model | CC | Resp | `reasoning.effort` values (default in **bold**) | CC tools + effort ≠ `none` | Source |
|---|---|---|---|---|---|
| `gpt-6-astra` | Supported | Supported | low, medium, high, xhigh, max (`none` returns HTTP 400) | **No tool calling on CC at all** | [page](https://developers.openai.com/api/docs/models/gpt-6-astra.md), [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) |
| `gpt-6.1-sol` | Supported | Supported | low, **medium**, high, xhigh, max (no none or minimal) | **No tool calling on CC** ("Chat Completions is supported without tool calling") | [page](https://developers.openai.com/api/docs/models/gpt-6.1-sol.md) |
| `gpt-6-sol` | Supported | Supported | none, low, **medium**, high, xhigh, max | Rejected; CC function calling "only with `reasoning_effort` set to `none`" | [page](https://developers.openai.com/api/docs/models/gpt-6-sol.md) |
| `gpt-6-luna` | Supported | Supported | none, low, **medium**, high, xhigh, max | Rejected; same as gpt-6-sol | [page](https://developers.openai.com/api/docs/models/gpt-6-luna.md) |
| `gpt-5.6-sol` (alias `gpt-5.6`) | Supported | Supported | none, low, **medium**, high, xhigh, max | Rejected (migration guide plus observed 400s) | [page](https://developers.openai.com/api/docs/models/gpt-5.6-sol.md) |
| `gpt-5.6-terra` | Supported | Supported | none, low, **medium**, high, xhigh, max | Rejected (observed 400) | [page](https://developers.openai.com/api/docs/models/gpt-5.6-terra.md) |
| `gpt-5.6-luna` | Supported | Supported | none, low, **medium**, high, xhigh, max | Rejected (observed 400) | [page](https://developers.openai.com/api/docs/models/gpt-5.6-luna.md) |
| `gpt-5.5` | Supported | Supported | none, low, **medium**, high, xhigh | Rejected (observed 400) | [page](https://developers.openai.com/api/docs/models/gpt-5.5.md) |
| `gpt-5.4` | Supported | Supported | **none**, low, medium, high, xhigh | Rejected (observed 400; "Starting with GPT-5.4") | [page](https://developers.openai.com/api/docs/models/gpt-5.4.md) |
| `gpt-5.4-mini` | Supported | Supported | **none**, low, medium, high, xhigh | Presumed rejected ("Starting with GPT-5.4"); no direct report found | [page](https://developers.openai.com/api/docs/models/gpt-5.4-mini.md) |
| `gpt-5.2` | Supported | Supported | **none**, low, medium, high, xhigh | Not covered by OpenAI's statement | [page](https://developers.openai.com/api/docs/models/gpt-5.2.md) |
| `gpt-5.1` | Supported | Supported | **none**, low, medium, high | Not covered | [page](https://developers.openai.com/api/docs/models/gpt-5.1.md) |
| `gpt-5` | Supported | Supported | minimal, low, medium, high | Not covered | [page](https://developers.openai.com/api/docs/models/gpt-5.md) |
| `o3`, `o4-mini` | Supported | Supported | (page extract did not show the list; historically low/medium/high, unverified this session) | Not covered | [o3](https://developers.openai.com/api/docs/models/o3.md), [o4-mini](https://developers.openai.com/api/docs/models/o4-mini.md) |
| `gpt-5.5-pro` | **Not supported** | Supported | medium, **high**, xhigh | n/a (Responses only) | [page](https://developers.openai.com/api/docs/models/gpt-5.5-pro.md) |
| `gpt-5.4-pro` | **Not supported** | Supported | **medium**, high, xhigh | n/a | [page](https://developers.openai.com/api/docs/models/gpt-5.4-pro.md) |
| `gpt-5.2-pro` | **Not supported** | Supported | medium, high, xhigh | n/a | [page](https://developers.openai.com/api/docs/models/gpt-5.2-pro.md) |
| `gpt-5-pro` | **Not supported** | Supported | high only | n/a | [page](https://developers.openai.com/api/docs/models/gpt-5-pro.md) |
| `o3-pro` | **Not supported** | Supported | (not shown) | n/a | [page](https://developers.openai.com/api/docs/models/o3-pro.md) |

## Notes

- **Every pro model ID is Responses-only.** The pages share near-identical wording, for example gpt-5.4-pro: "GPT-5.4 Pro is available in the Responses API only to enable support for multi-turn model interactions before responding to API requests, and other advanced API features in the future. Since GPT-5.4 Pro is designed to tackle tough problems, some requests may take several minutes to finish. To avoid timeouts, try using background mode." Kiln lists `gpt-5.2-pro` and `gpt-5.4-pro`. A plain Chat Completions call to either model cannot succeed against OpenAI directly.
- **Pro is becoming a mode, not a model.** For GPT-5.6 and GPT-6, pro is `reasoning.mode: "pro"`, which exists only in Responses ([latest-model guide](https://developers.openai.com/api/docs/guides/latest-model)). The deprecations page lists `gpt-5.6-sol` (`reasoning.mode: pro`) as the replacement for `gpt-5-pro`, `o3-pro` and `o1-pro`.
- The SDK's `ResponsesModel` type ([responses_model.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/shared/responses_model.py)) lists the IDs that are valid only for Responses: `o1-pro`, `o3-pro`, `o3-deep-research`, `o4-mini-deep-research`, `computer-use-preview`, `gpt-5.5-pro`, `gpt-5-codex`, `gpt-5-pro`, `gpt-5.1-codex-max`, `gpt-daybreak-blue-latest`, `gpt-daybreak-red-latest`, `gpt-5.6-cyber`, `gpt-rosalind-research`. (`gpt-5.2-pro` appears in the shared `ChatModel` literal, but its model page says CC is "Not supported". Trust the model page. The SDK literal is only a typing hint.)
- OpenAI's [March 2025 Responses launch post](https://openai.com/index/new-tools-for-building-agents/) gives the rule behind this: "We'll keep releasing new models to Chat Completions whenever their capabilities don't depend on built-in tools or multiple model calls." Pro models make multiple model calls, so they stay off Chat Completions.
- **Defaults differ by model.** GPT-5.1, 5.2 and 5.4 default to `none` (no reasoning). GPT-5.5, 5.6 and 6.x default to `medium`. A Kiln run that sends no effort therefore gets no reasoning on gpt-5.4 but medium reasoning on gpt-5.5.
- **`max`** is new with GPT-5.6. It is supported on GPT-5.6 and the GPT-6 family, and not on GPT-5.5 or earlier, per those model pages.
- **`minimal`** appears only on `gpt-5` (and probably `gpt-5-mini`/`gpt-5-nano`, which were not fetched). The GPT-6 guide says: "If your existing request uses `minimal`, start with `low`".

## Deprecations relevant to Kiln's OpenAI list (FYI)

From the [deprecations page](https://developers.openai.com/api/docs/deprecations.md):
- Already shut down: `gpt-5-chat-latest` (2026-07-23), `gpt-5.2-chat-latest` and `gpt-5.3-chat-latest` (2026-08-10).
- Shutting down 2026-10-23: `o1`, `o3-mini`, `o4-mini`, `gpt-4.1-nano`, `o1-pro`, among others.
- Shutting down 2026-12-11: the `gpt-5-2025-08-07`, `gpt-5-mini-2025-08-07` and `gpt-5-nano-2025-08-07` snapshots, plus `gpt-5-pro-2025-10-06`, `o3-2025-04-16` and `o3-pro-2025-06-10`.
