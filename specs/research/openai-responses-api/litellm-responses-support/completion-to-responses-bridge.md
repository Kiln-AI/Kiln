# The reverse bridge: `litellm.completion()` → `/v1/responses`

This doc covers how `litellm.completion()` / `acompletion()` can call OpenAI's Responses API while the caller keeps the chat-completions interface: messages in, `ModelResponse` with `choices[0].message` out. All source references are to the installed `litellm==1.102.0`. "Probe X" refers to the wire captures in [probe-evidence.md](./probe-evidence.md).

## 1. When `completion()` goes to Responses

The decision is made by `responses_api_bridge_check()` (`main.py:1047`). It runs twice inside `completion()`. The first call is early, with only the model and provider. The second call is late, with `tools`, `reasoning_effort`, the reasoning-summary aliases and `api_base`. If the result is `mode == "responses"`, `completion()` returns `litellm.completion_extras.responses_api_bridge.completion(...)` (`main.py:5616-5635`).

A request is routed to Responses when any of these holds:

1. **Global flag.** `litellm.route_all_chat_openai_to_responses = True`, or the env var `LITELLM_ROUTE_ALL_CHAT_OPENAI_TO_RESPONSES=true`. It applies only to `custom_llm_provider == "openai"`. The docs mark it "[BETA]" and say "Azure OpenAI is unaffected" ([OpenAI provider docs](https://docs.litellm.ai/docs/providers/openai)). Probe U: `openai/gpt-4.1` went to `/v1/responses`.
2. **`responses/` model prefix.** For example `openai/responses/gpt-5.5`, `azure/responses/<deployment>`, `openrouter/responses/openai/gpt-5.5`. `get_llm_provider` strips the provider, and the check sees `responses/...`. For OpenAI the cost-map lookup on `responses/gpt-5.5` finds no `mode`, so the prefix sets it. For Azure and others the lookup raises, and the `except` branch handles `model.startswith("responses/")`. The bridge then calls `responses()` with `f"{custom_llm_provider}/{model}"`. Verified for OpenAI (probes E–H, P, Q–T), OpenRouter (probe L → `/v1/responses`, body `model: "openai/gpt-5.5"`) and Azure (probe M → `/openai/responses?api-version=...`). Docs, quoted: "Option A, per-request prefix: Use the `openai/responses/` model prefix."
3. **The cost map says `mode: "responses"`.** In the bundled 1.102.0 map, 139 entries have this. The OpenAI ones (25): `codex-mini-latest`, `gpt-5-codex`, `gpt-5.1-codex`, `-codex-max`, `-codex-mini`, `gpt-5.2-codex`, `gpt-5.3-codex`, `gpt-5-pro` (+dated), `gpt-5.2-pro` (+dated), `gpt-5.4-pro` (+dated), `gpt-5.5-pro` (+dated), `o1-pro` (+dated), `o3-pro` (+dated), `o3-deep-research` (+dated), `o4-mini-deep-research` (+dated), `gpt-daybreak-red-latest`, `gpt-daybreak-blue-latest`. Azure has 25 (`azure/gpt-5-pro`, `azure/o3-pro`, `azure/gpt-5.x-codex*`, `azure/gpt-5.x-pro`, ...). **No `openrouter/*` entry has `mode: responses`.** `openrouter/openai/gpt-5-pro`, `.../gpt-5.4-pro` and `.../o3-pro` are all `mode: chat`. So pro and codex models through OpenRouter stay on OpenRouter's chat completions unless you add the `responses/` prefix. Probe F: `openai/gpt-5.5-pro` went to `/v1/responses` with no prefix.
4. **GPT-5.4+ with function tools and active reasoning, on OpenAI or Azure.** Verbatim condition (1.102.0):

```python
    if (
        custom_llm_provider in ("openai", "azure")
        and model_info.get("mode") != "responses"
        and OpenAIGPT5Config.is_model_gpt_5_model(model)
        and not OpenAIGPT5Config.is_model_gpt_5_search_model(model)
        and (
            (reasoning_effort is not None and reasoning_summary is not None)
            or (
                OpenAIGPT5Config.is_model_gpt_5_4_plus_model(model)
                and has_function_tool
                and reasoning_active
                and (reasoning_effort is not None or on_constraint_enforcing_endpoint)
            )
        )
    ):
        model_info["mode"] = "responses"
```

   The in-code rationale, verbatim: "OpenAI enables reasoning by default for these models (unset reasoning_effort means medium server-side), and Chat Completions rejects function tools whenever reasoning is on ("Function tools with reasoning_effort are not supported ... use /v1/responses or set reasoning_effort to 'none'"), so only an explicit ``"none"`` keeps the request chat-servable."

   - `is_model_gpt_5_4_plus_model` matches `gpt-5.N` with N ≥ 4 and anything starting with `gpt-6`.
   - `on_constraint_enforcing_endpoint` is true for Azure, the default OpenAI base, or any `*.api.openai.com` host. With a custom `api_base`, the auto-route only fires when `reasoning_effort` is set explicitly.
   - **Older GPT-5 (gpt-5, 5.1, 5.2):** routed only when a reasoning-summary alias (`reasoning_summary`/`reasoningSummary`) is present together with `reasoning_effort`. Tools plus effort alone stay on chat.

5. `web_search_options` on `xai` (not relevant to Kiln).

### Decision matrix, verified by calling `responses_api_bridge_check` directly (1.102.0, local cost map)

| provider/model | tools | reasoning_effort | → route |
|---|---|---|---|
| openai/gpt-5.5 | yes | unset (default base) | **responses** |
| openai/gpt-5.5 | yes | `none` | chat |
| openai/gpt-5.5 | no | `high` | chat |
| openai/gpt-5.4-mini | yes | `low` | **responses** |
| openai/gpt-5.2 | yes | `high` | chat |
| openai/gpt-5.2 | no | `high` + summary alias | **responses** |
| azure/gpt-5.5 | yes | unset | **responses** |
| azure/my-deploy (custom deployment name) | yes | `high` | chat (no match on name) |
| openrouter/openai/gpt-5.5 | yes | `high` | chat |
| openai/gpt-6-astra | yes | `high` | **responses** |
| openai/o3 | yes | `high` | chat |
| openai/gpt-5.5-pro, o3-pro, gpt-5.1-codex, gpt-5.3-codex | – | – | **responses** (cost map) |

Notes on this table:
- Azure custom deployment names need `azure/responses/<name>` or `model_info: {mode: responses}`. The [reasoning docs](https://docs.litellm.ai/docs/reasoning_content) say so: "Auto-routing relies on the deployment name matching the `gpt-5.4*` pattern."
- Doc inconsistency: the [OpenAI provider page](https://docs.litellm.ai/docs/providers/openai) still says "LiteLLM drops `reasoning_effort` from `gpt-5.4` and newer ... requests to `litellm.completion()` that include tools". In the same callout it also says LiteLLM "auto-routes these requests to `/v1/responses`". The 1.102.0 code does not drop the param. It auto-routes. Probe B confirms: `openai/gpt-5.5` + tools + `reasoning_effort="high"` was sent to `/v1/responses` with `reasoning: {effort: "high"}`. The Azure GPT-5 config comment agrees: "Azure gpt-5.4+ with tools + reasoning_effort is now routed to the Responses API bridge (same as OpenAI), so we no longer need to drop reasoning_effort here." (`llms/azure/chat/gpt_5_transformation.py`).

### Cost-map caveat: the routing can change without a LiteLLM upgrade
Branch 3 reads `litellm.model_cost`. By default, at import time, LiteLLM **fetches the cost map from a remote URL** and only falls back to the bundled copy on failure. The `get_model_cost_map` docstring says: "If `LITELLM_LOCAL_MODEL_COST_MAP` is set ... uses the local backup only. Otherwise fetches from `url`". So the set of models that are silently bridged can change on the next app start. Kiln does not set `LITELLM_LOCAL_MODEL_COST_MAP` (grep of `libs/`, `app/`). This is my inference from the code; I did not observe a live change.

## 2. What the bridge sends (chat params → Responses request)

Implementation: `completion_extras/litellm_responses_transformation/transformation.py` (`LiteLLMResponsesTransformationHandler`, 1,630 lines) and `handler.py`. The bridge builds the request and then calls `litellm.responses()` / `aresponses()`. So the native-provider path described in [responses-api-surface.md](./responses-api-surface.md) applies after translation.

| Chat Completions input | Responses request | Evidence |
|---|---|---|
| Leading `system` messages (string content) | `instructions` (several are joined with a space) | probes B, E. A system message after a non-system message stays as an input item ("Keep mid-conversation system messages in input", PR #40269, v1.102.0). |
| `user`/`assistant` messages | `input` items `{type: "message", role, content: [{type: "input_text"/"output_text"...}]}` | probe B |
| assistant `tool_calls` | `{type: "function_call", call_id, name, arguments}` | probe P |
| `role: "tool"` messages | `{type: "function_call_output", call_id, output: [{type: "input_text", text}]}`. Output is always wrapped in a list. Open issue [#34978](https://github.com/BerriAI/litellm/issues/34978) says this breaks strict non-OpenAI backends. | probe P |
| assistant `reasoning_items` (LiteLLM extension field), else `thinking_blocks` | `{type: "reasoning", id, summary, encrypted_content}` placed before the assistant output | probe P |
| `max_tokens` / `max_completion_tokens` | `max_output_tokens` | probe S |
| `tools` (function) | flat `{type: "function", name, description, parameters, strict}`. **`strict` is sent as `null` when the chat tool did not set it.** | probes B, S |
| `tool_choice` `"required"` / named function | `"required"` / `{type: "function", name}` | probes S, T |
| `parallel_tool_calls` | same | probe S |
| `response_format` `json_schema` | `text: {format: {type: "json_schema", name, schema, strict}}`. `strict` defaults to `False` if absent. `json_object` and `text` are passed through. | probe E |
| `reasoning_effort` string | `reasoning: {effort}`. If `litellm.reasoning_auto_summary` or `LITELLM_REASONING_AUTO_SUMMARY=true`, `summary: "detailed"` is added. | probes B, E |
| `reasoning_effort` dict `{"effort", "summary"}` | `reasoning` passed through verbatim | probe G |
| `include=[...]`, `store=...` | passed through (they are `ResponsesAPIOptionalRequestParams` keys) | probe G |
| `temperature` with reasoning active on GPT-5 | dropped when `drop_params=True`, otherwise `UnsupportedParamsError` | probe R |
| `top_logprobs` | passed through | probe H |
| **`logprobs=True`** | **silently dropped.** There is no `include: ["message.output_text.logprobs"]` and no logprobs mapping in either direction (grep for `logprob` in the bridge finds nothing). | probe H |
| **`verbosity`** | **silently dropped in 1.102.x.** Fixed in 1.104.0, which maps it to `text.verbosity` (diff below). | probe Q |
| `previous_response_id` | passed through. The debug log says "Warning ignoring previous response ID", but the key is in the optional-params set. | code |
| `web_search_options` | appended as a `{type: "web_search"}` tool | code |
| `store` | **not set unless the caller passes it.** OpenAI's server default then applies. | probe B (no `store` key) |

In 1.102.x, `_map_reasoning_effort` returns `None` for a string outside `REASONING_EFFORT` (`none|minimal|low|medium|high|xhigh|max`). 1.104.0 forwards any string instead ("Forward non-enum reasoning_effort through the Responses bridge instead of dropping it - PR #42452", [v1.104.0 notes](https://docs.litellm.ai/release_notes/v1.104.0/v1-104-0)).

## 3. What comes back (Responses output → `ModelResponse`)

`_convert_response_output_to_choices` and `transform_response`:

- A `message` output item becomes `Choices(message=Message(content=text, reasoning_content=<joined summary text>, reasoning_items=[...]))`, with `finish_reason="stop"`.
- `function_call` items are collected into **one** trailing choice with `tool_calls` and `finish_reason="tool_calls"`.
- **Bug, confirmed in 1.102.0 and still present in the code through 1.105.0rc1:** when the model writes text *and* calls a tool in the same turn, the result has **two choices**. `choices[0]` holds the text with `finish_reason="stop"` and no tool calls. `choices[1]` holds the tool calls. Probe B reproduces it: `n_choices: 2 finish: ['stop', 'tool_calls']`, and `choices[0].message.tool_calls` is empty. A client that reads only `choices[0]` loses the tool call. The upstream report is [#43316](https://github.com/BerriAI/litellm/issues/43316): "Responses bridge returns a narrated tool call as TWO chat choices ... so chat clients lose the tool call", affected "v1.102.1 and main". The tracker shows it **closed on 2026-10-03**. I could not see the close reason. A diff of `transformation.py` between 1.102.0, 1.104.0 and 1.105.0rc1 shows `_convert_response_output_to_choices` unchanged, so no released version fixes it as of 2026-10-05.
- **Bug: only the last reasoning item survives with `stream=False`.** `pending_reasoning_item` is overwritten for each reasoning item ([#43620](https://github.com/BerriAI/litellm/issues/43620), open, v1.102.1). With the two-choice split above, the reasoning item goes onto the text choice, not the tool-call choice. In probe B, `reasoning_items` was on `choices[0]`.
- `reasoning_content` is the joined **summary** text. It is `''`/`None` unless a summary was requested (`reasoning: {summary: ...}`, or `reasoning_auto_summary`) and the org is allowed to receive summaries. Raw `reasoning_text` content is dropped ([#40654](https://github.com/BerriAI/litellm/issues/40654), open).
- An `incomplete` status maps to `finish_reason` `length` or `content_filter`.
- Usage: `_transform_response_api_usage_to_chat_usage` maps `input_tokens`→`prompt_tokens`, `output_tokens`→`completion_tokens`, `input_tokens_details.cached_tokens`→`prompt_tokens_details.cached_tokens`, and `output_tokens_details.reasoning_tokens`→`completion_tokens_details.reasoning_tokens` (probe B).
- Cost: `response._hidden_params["response_cost"]` is filled for bridged calls (probe B: `0.000632` for 10 in / 20 out on gpt-5.5). `logging_obj.call_type` is set to `responses`.
- `response.id` is the decoded upstream response id. The model name is restored without the `responses/` prefix.
- Tool-call id: the bridge prefers `call_id`. It falls back to the item `id` (`fc_...`) when `call_id` matches the regex `call_\d+`. That heuristic exists for Bedrock Mantle's index-style ids (`_tool_call_id_from_responses_item`). Real OpenAI call ids (`call_<random>`) are not affected. A test mock using `call_1` will be.

## 4. Streaming through the bridge

Verified with an SSE mock (probe_stream.py, `acompletion(model="openai/responses/gpt-5.5", stream=True, tools=..., reasoning_effort="low")`):

- `response.reasoning_summary_text.delta` → `delta.reasoning_content`
- `response.output_text.delta` → `delta.content`
- `response.output_item.added` (function_call) → a `delta.tool_calls[0]` with `id`/`name`, then `function_call_arguments.delta` → argument chunks with the same `index`
- the `response.output_item.done` of the reasoning item → a chunk with `delta.reasoning_items` (it carries `encrypted_content`)
- `response.completed` → a chunk with `finish_reason="tool_calls"`, then a final chunk with `usage`
- `litellm.stream_chunk_builder(chunks)` rebuilt **one** choice: content `"Hi there"`, `tool_calls=['add']`, reasoning `"plan"`, usage 30. **The streaming path does not have the two-choice bug.**
- Harmless Pydantic warning seen: `PydanticSerializationUnexpectedValue(Expected ResponseAPIUsage ...)`.

Related open streaming issues: [#36992](https://github.com/BerriAI/litellm/issues/36992) (v1.96.2). Plain `completion(model="gpt-5.5", stream=True, reasoning_effort="high")` on the **chat** path streams nothing for about 79s, because chat completions does not stream reasoning summaries. The bridge path emits summary deltas. Also [#42955](https://github.com/BerriAI/litellm/issues/42955) (a streaming fallback replays a delivered tool call), [#43817](https://github.com/BerriAI/litellm/issues/43817) (`url_citation` annotations dropped when streaming) and [#38511](https://github.com/BerriAI/litellm/issues/38511) (the error handler masks the original error on the bridge iterator).

## 5. Multi-turn reasoning state

Docs, quoted: "For multi-turn conversations you need `reasoning_items`: structured blocks that include the `encrypted_content` token OpenAI uses to restore reasoning state on the next request. Pass `include=["reasoning.encrypted_content"]` on every call where you want that token returned." ([OpenAI provider docs](https://docs.litellm.ai/docs/providers/openai)). Callers have to copy `message.reasoning_items` onto the assistant message they send back. The bridge then emits them as `reasoning` input items (probe P). If they are not echoed back, nothing breaks: the request is still valid and the model just loses its prior reasoning. If a caller wants a stateless setup (`store=False`), it has to pass `store=False` itself. The bridge does not add it.

## 6. Size of the "bridge vs direct `responses()`" trade-off (LiteLLM view only)

Using the bridge keeps `ModelResponse`/`choices` shapes, streaming chunk shapes, `usage` and cost, so a chat-completions adapter keeps working. The gaps a caller has to handle are: the two-choice split (merge the choices, or fix it upstream), logprobs (not supported through the bridge), `verbosity` (dropped in 1.102), raw reasoning text (dropped), and only the last reasoning item when not streaming. Calling `litellm.responses()` directly avoids all of these. The caller then owns the input/output translation and the streaming event handling. How this maps onto Kiln's adapter is subtopic 3.
