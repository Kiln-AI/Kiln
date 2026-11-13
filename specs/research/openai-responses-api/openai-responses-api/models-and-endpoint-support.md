# Models: endpoint support, effort values, and Responses-only features

Model pages, guides, and changelog fetched 2026-10-30. The list covers the OpenAI-direct models in Kiln's model list (`libs/core/kiln_ai/adapters/ml_model_list.py`) that are GPT-5.2 or newer, plus the general rule for older ones.

## The rule behind Kiln's workaround

OpenAI's migration guide states it directly:

> "Reasoning models have a richer experience in the Responses API with improved tool usage. Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`."
> — [Migrate to the Responses API, "Additional differences"](https://developers.openai.com/api/docs/guides/migrate-to-responses)

The error OpenAI returns (wording reported for GPT-5.6 models; quoted by Microsoft Learn, an OpenAI community thread, and several third parties):

```text
Function tools with reasoning_effort are not supported for gpt-5.6-sol in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.
```

Returned as HTTP 400, `"type": "invalid_request_error"`, `"param": "reasoning_effort"` per third-party reports. Sources: [Azure reasoning models (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning); [OpenAI community, opened 2026-07-11](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454); [LibreChat #14231](https://github.com/LibreChat-AI/LibreChat/issues/14231) (gpt-5.6-terra); [LangChain PR #38860](https://github.com/langchain-ai/langchain/pull/38860) (gpt-5.6-luna); [AIVAX blog, 2026-10-13](https://aivax.net/blog/function-tools-reasoning-effort-not-supported-chat-completions/) (`param: reasoning_effort`).

OpenAI support's only public response (2026-09-07): "Responses supports the tool workflow, but we haven't confirmed a fix for this exact Chat Completions combination." ([community thread](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454)) Read: this is intended, not a bug that will be fixed.

### Unresolved: does omitting `reasoning_effort` also trigger it?

Third-party sources disagree:

- [ObjectGraph, 2026-09-03](https://objectgraph.com/blog/openai-function-tools-reasoning-effort-400/): with gpt-5.6-sol, "you can get this back even though your request never mentions reasoning... The model reasons at `medium` effort when you send nothing." LangChain's PR makes the same claim for GPT-5.6 ("GPT-5.6 uses a non-`none` reasoning effort by default, so OpenAI rejected the request").
- [APIYI docs](https://docs.apiyi.com/en/api-capabilities/openai/responses-migration): "Omitting `reasoning_effort` does not trigger it. On the `gpt-5.6-luna` route that reproduces the 400 deterministically, all four effort levels returned 400, while omitting the parameter returned `tool_calls` correctly 6 times out of 6." (through their gateway)

OpenAI's docs do not say. Defaults matter here: GPT-5.4 and GPT-5.2 default to `none`; GPT-5.5, GPT-5.6, and GPT-6 Sol/Luna/6.1 Sol/6.1 Terra default to `medium`. Kiln should not rely on omission; it should either send `none` or use Responses. (No API key was available to test.)

## Per-model table

"Chat tools" = whether function tools work on `/v1/chat/completions`.

| Model id | `reasoning.effort` values (default) | Chat Completions endpoint | Chat tools | Source |
| --- | --- | --- | --- | --- |
| `gpt-6-astra` | low, medium, high, xhigh, max. `none` → HTTP 400 | Supported | **No** | [model page](https://developers.openai.com/api/docs/models/gpt-6-astra), [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [changelog 2026-09-03](https://developers.openai.com/api/docs/changelog) |
| `gpt-6.1-sol` | low, medium (default), high, xhigh, max. No `none`/`minimal` | Supported | **No** ("Tool calling requires the Responses API.") | [model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |
| `gpt-6.1-terra` | none, low, medium (default), high, xhigh, max | Supported | **No** ("Tool calling requires the Responses API.", even though it supports `none`) | [model page](https://developers.openai.com/api/docs/models/gpt-6.1-terra), [GPT-6 guide](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra) |
| `gpt-6-sol` | none, low, medium (default), high, xhigh, max | Supported | Only with `reasoning_effort: "none"` | [model page](https://developers.openai.com/api/docs/models/gpt-6-sol) |
| `gpt-6-luna` | none, low, medium (default), high, xhigh, max | Supported | Only with `none` | [model page](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| `gpt-5.6-sol` (`gpt-5.6` alias) | none, low, medium (default), high, xhigh, max | Supported | Only with `none` | [model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol), migration guide rule, error text above |
| `gpt-5.6-terra` | none, low, medium (default), high, xhigh, max | Supported | Only with `none` | [model page](https://developers.openai.com/api/docs/models/gpt-5.6-terra) |
| `gpt-5.6-luna` | none, low, medium (default), high, xhigh, max | Supported | Only with `none` | [model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna) |
| `gpt-5.5` | none, low, medium (default), high, xhigh | Supported | Only with `none` | [model page](https://developers.openai.com/api/docs/models/gpt-5.5), migration guide rule |
| `gpt-5.5-pro` | medium, high (default), xhigh | **Not supported** (Responses + Batch only) | n/a | [model page](https://developers.openai.com/api/docs/models/gpt-5.5-pro) |
| `gpt-5.4` | none (default), low, medium, high, xhigh | Supported | Only with `none` | [model page](https://developers.openai.com/api/docs/models/gpt-5.4), migration guide rule |
| `gpt-5.4-pro` | medium (default), high, xhigh | **Not supported** (Responses only; Batch not supported) | n/a | [model page](https://developers.openai.com/api/docs/models/gpt-5.4-pro) |
| `gpt-5.4-mini` | none (default), low, medium, high, xhigh | Supported | Not stated per model; the "starting with GPT-5.4" rule suggests only with `none` | [model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| `gpt-5.4-nano` | none (default), low, medium, high, xhigh. **Status: Deprecated** | Supported | Same as mini (not stated) | [model page](https://developers.openai.com/api/docs/models/gpt-5.4-nano) |
| `gpt-5.2-pro` | medium, high, xhigh | **Not supported** (Responses only) | n/a | [model page](https://developers.openai.com/api/docs/models/gpt-5.2-pro) |
| `gpt-5.2` and earlier GPT-5, o-series | model-specific | Supported | Not covered by the documented rule | migration guide ("Starting with GPT-5.4") |

Notes on the table:

- GPT-6 guide, verbatim: "Tool calling: Use the Responses API. GPT-6 Astra, GPT-6.1 Sol, and GPT-6.1 Terra support Chat Completions, but tool calling requires Responses. GPT-6 Sol and GPT-6 Luna support function calling in Chat Completions only with `reasoning_effort: "none"`. Use Responses for reasoning with tools." ([Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra))
- GPT-6 Astra's default effort is not stated on its model page or in the GPT-6 guide. The reasoning guide says GPT-6.1 Sol, GPT-6 Sol, and GPT-6 Luna default to `medium`; the reference's generic default is `medium`.
- The GPT-6 Astra page's "Supported tools" list omits `function_calling` while its "Supported features" list includes it. I treat this as a page inconsistency.
- Pro model pages say "available in the Responses API only to enable support for multi-turn model interactions before responding to API requests". GPT-5.5 Pro: "Reasoning.effort supports: medium, high (default) and xhigh." ([GPT-5.5 Pro](https://developers.openai.com/api/docs/models/gpt-5.5-pro))
- **SDK enum discrepancy:** the Responses reference's `ResponsesOnlyModel` enum lists `o1-pro`, `o3-pro`, `o3-deep-research`, `o4-mini-deep-research`, `computer-use-preview`, `gpt-5.5-pro`, `gpt-5-codex`, `gpt-5-pro`, `gpt-5.1-codex-max`, `gpt-daybreak-blue-latest`, `gpt-daybreak-red-latest`, `gpt-5.6-cyber`, `gpt-rosalind-research` (plus snapshots), but not `gpt-5.4-pro` or `gpt-5.2-pro`, whose model pages say Chat Completions is "Not supported". The model pages are the more specific source. ([API reference, `model`](https://developers.openai.com/api/reference/resources/responses/methods/create))
- The GPT-5.6 Sol model page notes promotional pricing ($4/$20) "available at least through November 21, 2026". ([model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol))

## Features that only exist on Responses

Documented as Responses-only, or absent from the Chat Completions reference:

| Feature | Evidence |
| --- | --- |
| Function tools with reasoning effort ≠ `none` on GPT-5.4+; any function tools on GPT-6 Astra, GPT-6.1 Sol, GPT-6.1 Terra | rule and table above |
| Pro models (`gpt-5.2-pro`, `gpt-5.4-pro`, `gpt-5.5-pro`, older `gpt-5-pro`, `o3-pro`, `o1-pro`) | model pages, `ResponsesOnlyModel` enum |
| Pro **mode** (`reasoning.mode: "pro"`, GPT-5.6 and GPT-6) | "support `standard` and `pro` reasoning modes in the Responses API" ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)); no `mode` field in the Chat reference |
| Reasoning summaries (`reasoning.summary`) | no summary field anywhere in the Chat Completions reference; [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) |
| Passing reasoning (CoT) between turns: reasoning items, `encrypted_content`, `reasoning.context` (persisted reasoning) | "Passing CoT exists only in the Responses API" ([Using GPT-5.4](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.4)) |
| `phase` on assistant messages | Responses item field only |
| `configuration_update` (mid-conversation effort change, GPT-6) | [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) |
| Built-in tools (web search, file search, code interpreter, MCP, computer use, tool search, shell, apply_patch, skills) | "With Chat Completions, you cannot use OpenAI-hosted tools natively" ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)) |
| `previous_response_id`, Conversations API, background mode, server-side compaction, WebSocket mode, async tool calling, mid-turn steering, multi-agent, Programmatic Tool Calling | guides listed in [llms.txt](https://developers.openai.com/api/docs/llms.txt) and the [changelog](https://developers.openai.com/api/docs/changelog) |
| 12h prompt-cache lifetime; cache prewarm | [Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) (references disagree on 12h, see [data-retention-caching-pricing.md](./data-retention-caching-pricing.md)) |
| Reusable prompt objects (`prompt`) | "Reusable prompts are not available in Chat Completions." ([changelog](https://developers.openai.com/api/docs/changelog)) |

Not Responses-only, despite expectations:

- **`max` effort**: in the Chat Completions `reasoning_effort` enum. ([Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create))
- **Structured outputs, JSON mode**: "Both Structured Outputs and JSON mode are supported in the Responses API, Chat Completions API, Assistants API, Fine-tuning API and Batch API." ([structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs))
- **Custom tools** (freeform input): shown for both APIs in the GPT-5.4 guide.
- **Verbosity**: top-level `verbosity` on Chat, `text.verbosity` on Responses.
- **Prompt cache options and breakpoints** (GPT-5.6+): present in both references.

Only on Chat Completions: `n > 1`, `stop`, `seed`, `frequency_penalty`, `presence_penalty`, `logit_bias`, `prediction` (Predicted Outputs), audio in/out (`modalities`, `audio`). See [request-response-shape.md](./request-response-shape.md#parameter-differences-from-the-two-api-references).

## The future of Chat Completions

What OpenAI says, verbatim:

- "While Chat Completions remains supported, Responses is recommended for all new projects." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- "Chat Completions remains supported, so you can migrate one user flow at a time." (same, "Incremental rollout checklist")
- "Future-proof: Future-proofed for upcoming models." (same, "Responses benefits")
- Chat Completions reference header: "Starting a new project? We recommend trying Responses to take advantage of the latest OpenAI platform features." ([Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create))
- The API Overview's "Choose the API surface" step lists Responses, Realtime, and Administration, and does not list Chat Completions. ([API Overview](https://developers.openai.com/api/reference/overview))
- Reasoning guide: "Reasoning models work better with the Responses API. While the Chat Completions API is still supported, you'll get improved model intelligence and performance by using Responses." ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning))
- GPT-5.5 / GPT-5.6 guides: "Use the Responses API for any reasoning, tool-calling, or multi-turn use case." / "Use the Responses API for reasoning, tool-calling, and multi-turn workflows." ([GPT-5.5](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.5), [GPT-5.6](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.6))
- Quality claim: "Using reasoning models, like GPT-5, with Responses will result in better model intelligence when compared to Chat Completions. Our internal evals reveal a 3% improvement in SWE-bench with same prompt and setup." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))

The [Deprecations page](https://developers.openai.com/api/docs/deprecations) lists no deprecation of Chat Completions. The Assistants API shut down on 2026-08-26 ("Migrate to the Responses API and Conversations API"); the legacy Completions endpoint's last models shut down 2026-09-28. ([changelog](https://developers.openai.com/api/docs/changelog), [Completions API](https://developers.openai.com/api/docs/guides/completions))

**Reading of the trend (inference):** Chat Completions is not deprecated, but each model generation since GPT-5.4 (March 2026) has narrowed what works there: tools-with-reasoning blocked (GPT-5.4), Pro models Responses-only, reasoning summaries and CoT passing Responses-only, pro mode and `configuration_update` Responses-only (GPT-5.6 / GPT-6), and tool calling entirely Responses-only for GPT-6 Astra, GPT-6.1 Sol and GPT-6.1 Terra. The GPT-6 Astra (2026-09-03) and GPT-6.1 Sol (2026-09-29) changelog entries both tell developers to use Responses for tool calling. A design that routes "every OpenAI model released after GPT-5.4" to Responses matches this direction.

## Other dated facts

- GPT-5.4 and GPT-5.4 Pro released 2026-03-05; GPT-5.4 mini/nano 2026-03-17 (snapshot dates). GPT-5.5 / 5.5 Pro: snapshot 2026-04-23. GPT-5.6 family: 2026-07-09. GPT-6 Astra: 2026-09-03. GPT-6 Sol / Luna: 2026-09-22. GPT-6.1 Sol: 2026-09-29. GPT-6.1 Terra: 2026-10-26. ([changelog](https://developers.openai.com/api/docs/changelog))
- "Open Responses: an open-source spec for building multi-provider, interoperable LLM interfaces built on top of the original OpenAI Responses API" announced Jan 15 (2026). ([changelog](https://developers.openai.com/api/docs/changelog))
