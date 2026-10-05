# What Kiln Sends Today, and What LiteLLM Does With It

Codebase investigation of this repo at commit `c215b3e4` (2026-10-05) plus offline probes of the installed `litellm==1.102.0` (no API calls). Everything here is from reading or running local code; web evidence is in [evidence.md](./evidence.md).

## How the thinking level reaches the wire

`LiteLlmAdapter.build_extra_body()` (`libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py` L561-673):

- Thinking level = `run_config.thinking_level` if set, else `provider.default_thinking_level`.
- Only sent when `provider.available_thinking_levels is not None`.
- OpenRouter + `openrouter_reasoning_object=True` → `reasoning: {"effort": <level>}`.
- Anthropic + `none` → nothing sent.
- Everything else (OpenAI, Azure OpenAI, OpenRouter without the flag) → `reasoning_effort: <level>`.

`build_completion_kwargs()` (L725-) spreads that dict into the **top-level** `litellm.acompletion()` kwargs (not into the OpenAI SDK's `extra_body`), together with `"drop_params": True`. So `reasoning_effort` goes through LiteLLM's per-provider param mapping, and LiteLLM is allowed to **silently drop** it.

Tools are added as `tools` + `tool_choice: "auto"` when the task has tools. Structured output mode `function_calling` also sends a forced `tools` / `tool_choice` (L531-559).

## Kiln's OpenAI-model catalogue (from `ml_model_list.py`)

| Model | OpenAI direct | OpenRouter | Azure OpenAI |
|---|---|---|---|
| GPT-6.1 Sol | levels low/medium/high/xhigh (no `max`: "rejects it with a 400; only /v1/responses accepts it"), **`supports_function_calling=False`** | low…max, `openrouter_reasoning_object=True` | — |
| GPT-6.1 Sol Pro, GPT-6 Sol Pro, GPT-6 Luna Pro | — | levels incl. `max`, reasoning object | — |
| GPT-6 Astra | low…max, **FC disabled** | low…max, reasoning object | — |
| GPT-6 Sol / Luna | none, low…max, **FC disabled** | same, reasoning object | — |
| GPT-5.6 Sol/Terra/Luna, GPT-5.5 | none, low, medium, high, xhigh, **FC disabled** | same, reasoning object | — |
| GPT-5.4 | same, **FC disabled** | same (bare `reasoning_effort`, FC on) | — |
| GPT-5.4 Pro, GPT-5.2 Pro | medium/high/xhigh, FC on | same, FC on | — |
| GPT-5.4 mini/nano | no thinking levels on OpenAI; levels on OpenRouter | | — |
| GPT-5.2, 5.1, 5 (+mini/nano) | levels per model, FC on | same | — |
| o1 / o3 / o3-mini / o4-mini (low/medium/high as separate Kiln models) | one level each | o4-mini only, no levels | one level each |
| GPT-4.1 / 4o | no levels | no levels | no levels |
| gpt-oss (Groq, Cerebras, Fireworks, Ollama, OpenRouter, Featherless) | — | no levels | — |

Every OpenAI-direct entry for GPT-5.4 and newer carries the same comment:

> `# OpenAI rejects reasoning_effort + tools on /v1/chat/completions`
> `# for gpt-5.4+. Disable function calling until Kiln routes these`
> `# models to /v1/responses.`

Every OpenRouter entry for GPT-5.5 and newer carries:

> `# Use OpenRouter's reasoning object so reasoning is preserved`
> `# when tools are sent (the bare reasoning_effort param is`
> `# silently dropped on tool calls for these models).`

Commit `1aed843a` (2026-10-01, "Add GPT-6.1 Sol") records a hands-on finding:

> "the OpenAI model page lists low/medium/high/xhigh/max, but /v1/chat/completions (which Kiln uses) rejects max with a 400 and only /v1/responses accepts it ... OpenRouter accepts max ... none and minimal are rejected everywhere."

So Kiln itself already documents two concrete Chat Completions failure modes: **reasoning + function tools on GPT-5.4+**, and **`max` on GPT-6.1 Sol**.

Azure in Kiln today only carries o-series models with thinking levels, plus GPT-4.x; no GPT-5.x/6 Azure entries. Azure is therefore not affected by the GPT-5.4+ restrictions in Kiln's current catalogue.

## The paid test

`test_thinking_level_paid.py::test_thinking_level_reasoning_content` parametrises every `(provider, model, level)` with `available_thinking_levels` for OpenRouter, **OpenAI**, Anthropic and Gemini. It uses `structured_output_mode="default"` and **no tools**, so it never exercises the reasoning+tools case. For a non-`none` level it asserts reasoning **content is present** (from `intermediate_outputs["reasoning"]` or a trace message's reasoning field).

Inference (not verified, no paid run): on OpenAI direct via Chat Completions the response carries no reasoning text (see [evidence.md](./evidence.md), section 5), so these OpenAI cases should fail that assertion unless LiteLLM bridges them to Responses and requests a summary. The bridge does not request a summary by default (`litellm.reasoning_auto_summary` is off). The test's exception lists cover Anthropic and Gemini adaptive models only, not OpenAI. Either the OpenAI cases fail today or nobody has run them with an OpenAI key recently; I could not tell which. The prerelease whitelist (`pytest_prerelease_whitelist.py` `PRERELEASE_THINKING_MODELS`) contains no OpenAI entries.

## What LiteLLM 1.102.0 does with Kiln's request (offline probes)

Probe script: `get_optional_params(..., drop_params=True)` and `litellm.main.responses_api_bridge_check(...)`, run with the bundled map (`LITELLM_LOCAL_MODEL_COST_MAP=True`) and with the default remote map (fetched from GitHub `main` at import time). No model calls.

### 1. LiteLLM already auto-routes the failing case to Responses

`responses_api_bridge_check()` in `litellm/main.py` (~L1047-1145) switches a `completion()` call to the Responses API when:

- the model's map entry has `mode: "responses"` (all `-pro` and `-codex` models), or
- provider is `openai`/`azure`, the model is GPT-5.4+ or any `gpt-6*` (`is_model_gpt_5_4_plus_model`), the request has a **function** tool, and reasoning is active (effort not `"none"`).

Source comment, verbatim:

> "gpt-5.4+: FUNCTION tools with reasoning active must be bridged. OpenAI enables reasoning by default for these models (unset reasoning_effort means medium server-side), and Chat Completions rejects function tools whenever reasoning is on ("Function tools with reasoning_effort are not supported ... use /v1/responses or set reasoning_effort to 'none'"), so only an explicit ``"none"`` keeps the request chat-servable."

Probe results (`custom_llm_provider="openai"`):

| model | effort | tools | routed to |
|---|---|---|---|
| gpt-6-sol | medium | function | **responses** |
| gpt-6-sol | none | function | chat |
| gpt-6.1-sol | medium | function | **responses** |
| gpt-5.4 | medium | function | **responses** |
| gpt-5.4 | none / no tools | | chat |
| gpt-5.2 | medium | function | chat (not affected) |
| gpt-5.4-pro, gpt-5.2-pro | any | any | **responses** (map `mode: responses`) |
| o3 | any | any | chat |

So, at the pinned LiteLLM version, Kiln's thinking level **already reaches** OpenAI's pro models (via the bridge), and a Kiln request with tools + reasoning on GPT-5.4+ would be bridged rather than 400. Kiln disables function calling on those entries anyway, so this path is unused. Whether the bridge is good enough for Kiln's multi-turn tool loop, streaming and trace saving belongs to the LiteLLM and integration subtopics.

### 2. Silent drops caused by `drop_params=True`

- **`xhigh` on models missing from the bundled map.** `OpenAIGPT5Config.map_openai_params` treats `xhigh` as opt-in. If the map entry lacks `supports_xhigh_reasoning_effort: true` and `drop_params` is on, LiteLLM pops `reasoning_effort` with no warning. The 1.102.0 bundled map has no entry for `gpt-6-sol`, `gpt-6-luna` or `gpt-6.1-sol`. Probe: `gpt-6-sol` + `xhigh` → `{}` with the bundled map, but `{'reasoning_effort': 'xhigh'}` with the remote map. Kiln does not set `LITELLM_LOCAL_MODEL_COST_MAP`, so normal runs use the remote map. If the fetch fails (offline, proxy, GitHub outage), LiteLLM falls back to the bundled map and **Kiln's "Extra High" quietly becomes the model default**. LiteLLM tracks this as [#40471](https://github.com/BerriAI/litellm/issues/40471) (open).
- **`xhigh` on gpt-5.1.** Probe: dropped. Kiln does not offer `xhigh` for GPT-5.1, so this is harmless.
- **OpenRouter `max` → `xhigh`.** `OpenrouterConfig.map_openai_params` rewrites `reasoning_effort="max"` to `"xhigh"` ("OpenRouter expects "xhigh" instead of "max""). Probe: `openrouter` + `openai/gpt-6-astra` + `max` → `xhigh`. Kiln's GPT-6 OpenRouter entries send the `reasoning` object instead, which skips this mapping. A future OpenRouter entry that offers `max` without `openrouter_reasoning_object=True` would silently get `xhigh`.
- **`none` is never gated** ([#40472](https://github.com/BerriAI/litellm/issues/40472)). `none` goes through to OpenAI even where the map says it is unsupported. The caller gets a real 400 from OpenAI, so this fails loudly. Kiln's level lists already omit `none` where OpenAI rejects it.

### 3. `max` on OpenAI direct

LiteLLM forwards `max` unchanged on chat (probe: gpt-6-astra/6.1-sol `max` → `'reasoning_effort': 'max'`). Whether OpenAI accepts it depends on the model and the date; see [evidence.md](./evidence.md), section 3. Before #38084 was fixed, the Responses bridge dropped `max` silently. In 1.102.0 `REASONING_EFFORT` includes `"max"` (`litellm/types/llms/openai.py` L1889), so the bridge now forwards it.
