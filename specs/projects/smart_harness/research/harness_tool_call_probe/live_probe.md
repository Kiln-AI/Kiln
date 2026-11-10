# Harness-written tool calls and thinking models: live probe

Date of the probe: 2026-11-10. All calls were made between 02:36 and 03:10 UTC.

This file reports live API behaviour only. It makes no design recommendation. A separate file in this folder, `docs_probe.md`, covers what the documentation says.

## The scenario

The harness, not the model, decides to call a tool. It runs the tool and then calls the model with a history that looks as if the model had made the call:

```
system
user("...")
assistant(tool_calls=[get_user_info()])   <- written by the harness: no reasoning text, no thinking block, no thought signature
tool(result)
-> the model is called here, with reasoning on
```

The claim under test: this breaks when reasoning is on. Anthropic would return a 400 ("final assistant message must start with a thinking block"), LiteLLM would silently drop the thinking parameter, and Gemini 3 would reject a function call that has no thought signature.

## What was observed, in short

Everything in this section was observed through OpenRouter. Nothing was tested against a provider's own API.

- **No request failed because the harness-written call had no reasoning attached.** 129 calls had such a call in their history. 124 succeeded, across 52 models and 20 upstream hosts. The 5 that failed were 3 OpenRouter routing refusals caused by the test account's privacy settings and 2 outages at one host (SiliconFlow, for `deepseek/deepseek-r1-0528`), which also failed the control call that had no harness-written call in it.
- **The 400 that the claim predicts for Anthropic did not occur.** That includes `anthropic/claude-haiku-4.5`, the one Claude model in the set that predates adaptive thinking, on four hosts: Amazon Bedrock, Anthropic, Google Vertex and Azure.
- **Gemini 3.x did not reject the call.** `google/gemini-3.1-pro-preview` and `google/gemini-3.8-flash` answered with reasoning on both Google AI Studio and Google Vertex. Five more Gemini 3.x models did on Google AI Studio.
- **LiteLLM did not drop or change the reasoning parameter because of the history.** The request body it sent to OpenRouter carried the same reasoning parameters in every scenario for a given model. Setting `litellm.modify_params = True` produced an identical body.
- **The model used the injected tool result every time it answered.** In 123 of the 124 successful calls the answer contained facts that exist only in the tool result. In the remaining one the model (`bytedance-seed/seed-1.6-flash`) called the tool again, and it did the same when its own tool call was passed back.
- **Reasoning came back after the harness-written call for 47 of the 52 models.** For 4 of the other 5, the natural flow (the model's own tool call passed back with its reasoning) also returned zero reasoning tokens on that call, so the harness-written call made no visible difference.
- **One model lost reasoning: `thinkingmachines/inkling-small` (host DeepInfra).** With the model's own call passed back it returned 115 to 239 reasoning tokens. With a harness-written call in the history it returned 0, in 8 of 8 calls, and 4 of those 8 answers were wrong. Adding any reasoning text to the harness-written message brought reasoning back. Details are in section 8.
- **Through Kiln's own adapter the case works today.** The existing resume path took a `prior_trace` ending in a harness-written call plus a tool result for all 7 models tried. No Kiln-side error fired, including the check for missing reasoning.
- **Kiln's resume path already sends model-made tool calls back without their signatures.** On the wire, a model-made call that Kiln passes back from a stored trace carries at most plain reasoning text. For Gemini it carries nothing and has the same shape as a harness-written call. Details are in section 7.

## Method

### Setup

- Kiln code at commit `b0842f3a` (later commits made during the probe changed only `specs/`). LiteLLM 1.102.0, httpx 0.28.1, Python 3.13.14.
- Every call went to `https://openrouter.ai/api/v1` through LiteLLM's `openrouter/` route, which is what Kiln's openrouter provider uses.
- Models and slugs were taken from the openrouter entries in `libs/core/kiln_ai/adapters/ml_model_list.py`.
- The tool is `get_user_info`, with no arguments. Its result is `{"name": "Dana Okafor", "plan": "enterprise", "city": "Lisbon", "account_id": "A-7731"}`.
- The user message asks the model to work out a support tier from the plan, the city and the account id, and to address the user by first name. The right answer is "Gold", hub "Aurora", for "Dana". None of that can be known without the tool result. The full text is in `probe_common.py` in the appendix.
- The harness-written call uses the id `call_kilnharness0001`, `content: null`, and no reasoning field of any kind.

### Layer 1: raw `litellm.acompletion`

The message history was built by hand. Every other parameter came from Kiln's own `LiteLlmAdapter.build_completion_kwargs`, called on a real adapter for that model on the openrouter provider with a thinking level set. So the model id, `temperature`, `top_p`, `drop_params`, tool definitions, `tool_choice`, `usage`, the `provider.order` list and the reasoning parameters are exactly what Kiln passes to LiteLLM. Two things were added that Kiln does not send:

- `max_tokens` (2500, or 2000 in the width sweep, or 1500 for `moonshotai/kimi-k3`), to cap spend.
- In the runs marked "pin", `provider: {"order": [<host>], "allow_fallbacks": false}`, to force one upstream host.

Scenarios:

| Id | History sent | Reasoning | Purpose |
|---|---|---|---|
| S0 | system, user | on | Control. Does the model call the tool by itself, and is reasoning returned? |
| S0n | system, user, the model's own tool call from S0 exactly as OpenRouter returned it (with `reasoning` and `reasoning_details`), tool result | on | Control. The natural flow, to compare with S1. |
| S0c | system, user with the account record written into the message | on | Control. Is reasoning returned at all for this model and these parameters? |
| S1 | system, user, harness-written call, tool result | on | The case in question. |
| S2 | same as S1 | off | Control. Off means Kiln's `none` level where the model has one. Otherwise the reasoning parameters were left out. |
| S3 | system, user, harness-written call, tool result, assistant text answer, second user message | on | Harness-written call in an earlier turn. |
| S4 | system, harness-written call, tool result, user | on | Harness-written call before the user's message. |
| S5 | system, user, harness-written call, tool result, the model's own call from S0 with its reasoning, tool result | on | A harness-written call followed by a signed model-made call in one turn. |
| W_user_after_tool | S1 plus a closing user message "Go ahead and answer my question." | on | Workaround candidate where S1 returned no reasoning. |

S4 was accepted by every model that was sent it, so the variant with a leading placeholder user message was not run.

Each scenario was run once. Repeats are marked in the tables.

### Layer 2: Kiln's adapter

`adapter_for_task(...)` with `KilnAgentRunConfigProperties` on the openrouter provider, a thinking level set, `AdapterConfig(allow_saving=False, ...)`, and `get_user_info` supplied as an unmanaged tool. Flows:

| Flow | What was called |
|---|---|
| natural_first | `invoke(question)` with `return_on_tool_call=True`. The model asks for the tool and Kiln returns. |
| natural_resume | Kiln's existing resume path with the model-made call: `invoke(input=[{tool_call_id, content}], prior_trace=<trace of natural_first>)`. |
| harness_resume | S1. `prior_trace = [system, user, harness-written call]`, `input = {"tool_call_id": "call_kilnharness0001", "content": <tool result>}`. The system and user messages are the ones Kiln's own formatter produces for the task. |
| harness_resume_stream | The same through `invoke_openai_stream`. |
| harness_premessage | S4. `prior_trace = [system, harness-written call, tool result]`, `input = <question>`. |
| natural_inloop | `invoke(question)` with `return_on_tool_call=False` and a tool Kiln can run. Shows what Kiln sends back for a model-made call inside one invoke. |

Layer 2 requests carry no `max_tokens`, because Kiln does not send one.

### How results were captured

`httpx.AsyncClient.send` was wrapped in the probe process. For every request it recorded the URL, the JSON body LiteLLM sent, the HTTP status, and the JSON OpenRouter returned. Headers were never recorded. LiteLLM's loggers were captured at WARNING and above. LiteLLM's debug mode was not used.

"Reasoning present" in the tables is `usage.completion_tokens_details.reasoning_tokens` from OpenRouter's raw response. The raw `reasoning` text and the `reasoning_details` entries were recorded too.

### How to read a table cell

`ok, r=167, used` means: HTTP 200, 167 reasoning tokens, and the answer states facts that are only in the tool result. `model calls tool` means the response was a tool call, not an answer. `wrong answer` means the answer named the wrong tier or hub; each of those was read by hand. `-` means not run. Two results separated by `/` are two runs. The "Reasoning params in the request body" column is taken from the captured HTTP body of the reasoning-on calls, not from the kwargs.

## Limitations

- **OpenRouter only.** There were no Anthropic, OpenAI or Google keys. OpenRouter sits between LiteLLM and every model host and can rewrite a request. What a provider's own API does with this history was not tested. In Kiln that matters for the `anthropic`, `gemini_api`, `vertex`, `openai` and `amazon_bedrock` providers, which use different LiteLLM routes.
- **The request OpenRouter sends on to the model host is not visible.** Statements about that leg are inferences and are marked as such.
- **One run per cell**, at temperature 1. Token counts vary from run to run.
- **Two endpoints could not be reached.** The test account's OpenRouter privacy settings exclude the first-party `deepseek` endpoint and the only endpoint of `qwen/qwen3-30b-a3b`. DeepSeek models were tested on Fireworks, Together, DeepInfra, Novita and Parasail only. The first-party Moonshot endpoint was reachable and was tested.
- **`deepseek/deepseek-r1-0528` gave no usable result.** Its host returned 502 and 503 on the control call and on S1.
- **The task is easy.** Models with adaptive thinking sometimes skip thinking on it. Where that made a result ambiguous the natural flow (S0n) is the comparison, and `anthropic/claude-sonnet-5.5` was repeated at a higher effort level.
- **Layer 1 adds `max_tokens`.** Layer 2 has no such cap.
- **Not tested:** parallel harness-written calls, harness-written calls with arguments, structured output tasks, prompt caching, and editing or removing a harness-written call on a later request.

## Results

### 1. Main set, with Kiln's own provider order

Thinking level used per model: `high` for Claude Haiku 5.5, Claude Sonnet 5.5, Gemini 3.8 Flash, DeepSeek V4.1 Flash and GLM 5.3 Flash; `medium` for Claude Haiku 4.5, GPT-5.6 Luna and GPT-6 Luna; `low` for Gemini 3.1 Pro, Gemini 4 Argon, Kimi K3 and Grok 4.3. Kimi K2 Thinking has no levels in Kiln.

| Model | Run | Host that served it | Reasoning params in the request body | S0 | S0n | S0c | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | base | Amazon Bedrock | `{"reasoning": {"effort": "high"}}` | ok, r=0, model calls tool | ok, r=158, used | ok, r=342, model calls tool | ok, r=167, used | ok, r=154, used | ok, r=227, used | ok, r=193, used |
| `anthropic/claude-haiku-4.5` | base | Amazon Bedrock | `{"reasoning": {"effort": "medium"}}` | ok, r=68, model calls tool | ok, r=0, used | ok, r=315, used | ok, r=0, used | ok, r=0, used | ok, r=308, used | ok, r=293, used |
| `anthropic/claude-sonnet-5.5` | base | Amazon Bedrock | `{"reasoning": {"effort": "high"}}` | ok, r=0, model calls tool | ok, r=0, used | ok, r=116, model calls tool | ok, r=0, used | ok, r=0, used | ok, r=129, used | ok, r=0, used |
| `google/gemini-3.8-flash` | base | Google AI Studio | `{"reasoning": {"enabled": true}, "reasoning_effort": "high"}` | ok, r=88, model calls tool | ok, r=832, used | ok, r=321, model calls tool | ok, r=893, used | ok, r=436, used | ok, r=859, used | ok, r=716, used |
| `google/gemini-3.1-pro-preview` | base | Google | `{"reasoning": {"enabled": true}, "reasoning_effort": "low"}` | ok, r=101, model calls tool | ok, r=266, used | ok, r=346, used | ok, r=333, used | ok, r=691, used | ok, r=196, used | ok, r=346, used |
| `openai/gpt-5.6-luna` | base | Amazon Bedrock | `{"reasoning": {"effort": "medium"}}` | ok, r=9, model calls tool | ok, r=54, used | ok, r=71, used | ok, r=42, used | ok, r=0, used | ok, r=50, used | ok, r=47, used |
| `deepseek/deepseek-v4.1-flash-1017` | base | Fireworks | `{"reasoning": {"effort": "high"}}` | ok, r=0, model calls tool | ok, r=118, used | ok, r=41, model calls tool | ok, r=84, used | ok, r=0, used | ok, r=99, used | ok, r=76, used |
| `moonshotai/kimi-k2-thinking` | base | Novita | `{"reasoning": {"exclude": false}}` | ok, r=62, model calls tool | ok, r=281, used | ok, r=306, used | ok, r=347, used | ok, r=236, used | ok, r=433, used | ok, r=684, used |
| `moonshotai/kimi-k3` | base | Fireworks | `{"reasoning": {"effort": "low"}}` | ok, r=5, model calls tool | ok, r=39, used | - | ok, r=44, used | - | - | ok, r=57, used |
| `z-ai/glm-5.3-flash` | base | Fireworks | `{"reasoning": {"effort": "high"}}` | ok, r=0, model calls tool | ok, r=59, used | ok, r=65, used | ok, r=55, used | ok, r=238, used | ok, r=60, used | ok, r=65, used |
| `x-ai/grok-4.3` | base | xAI | `{"reasoning": {"effort": "low"}}` | ok, r=118, model calls tool | ok, r=214, used | ok, r=486, used | ok, r=234, used | ok, r=0, used | ok, r=312, used | ok, r=238, used |
| `google/gemini-4-argon` | base | Google | `{"reasoning": {"enabled": true}}` | ok, r=0, model calls tool | ok, r=0, used | - | ok, r=0, used | - | - | ok, r=0, used |
| `openai/gpt-6-luna` | base | Amazon Bedrock | `{"reasoning": {"effort": "medium"}}` | ok, r=0, model calls tool | ok, r=47, used | - | ok, r=68, used | - | - | ok, r=54, used |

Notes on this table:

- Kiln's `provider.order` list contains `amazon-bedrock` and `azure`. So Claude and GPT models were served by Amazon Bedrock, not by Anthropic or OpenAI. Gemini models have no host in that list and OpenRouter picked Google AI Studio or Google Vertex (shown as "Google").
- `anthropic/claude-haiku-4.5`: S1 returned 0 reasoning tokens, and so did S0n, the natural flow with the model's own signed thinking block passed back. Reasoning came back when the last message was a user message (S3, S4).
- `anthropic/claude-sonnet-5.5` at `high` returned 0 reasoning tokens in S1, in S4 and in the natural flow S0n alike. At `xhigh` (next table) all three returned about 100.
- Four models called the tool in S0c although the record was in the message: Claude Haiku 5.5, Claude Sonnet 5.5, Gemini 3.8 Flash and DeepSeek V4.1 Flash. Reasoning tokens were returned on that call.
- Claude Haiku 5.5, both Gemini 3.x models, Kimi K2 Thinking and GLM 5.3 Flash returned reasoning tokens in S2 although no reasoning parameter was sent. Kiln has no `none` level for these models.
- `google/gemini-4-argon` returned 0 reasoning tokens in every scenario, including the natural flow. Its `reasoning_effort` never reached OpenRouter (section 6).

### 2. Same models pinned to one upstream host, and repeats

| Model | Run | Host that served it | Reasoning params in the request body | S0 | S0n | S0c | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | pin-anthropic | Anthropic | `{"reasoning": {"effort": "high"}}` | ok, r=23, model calls tool | ok, r=164, used | - | ok, r=140, used | ok, r=134, used | ok, r=223, used | ok, r=242, used |
| `anthropic/claude-haiku-5.5` | pin-google-vertex | Google | `{"reasoning": {"effort": "high"}}` | - | - | - | ok, r=141, used | - | - | - |
| `anthropic/claude-haiku-5.5` | pin-azure | Azure | `{"reasoning": {"effort": "high"}}` | - | - | - | ok, r=153, used | - | - | - |
| `anthropic/claude-haiku-4.5` | pin-anthropic | Anthropic | `{"reasoning": {"effort": "medium"}}` | ok, r=74, model calls tool | ok, r=0, used | - | ok, r=0, used | - | - | ok, r=252, used |
| `anthropic/claude-haiku-4.5` | pin-google-vertex | Google | `{"reasoning": {"effort": "medium"}}` | - | - | - | ok, r=0, used | - | - | - |
| `anthropic/claude-haiku-4.5` | pin-azure | Azure | `{"reasoning": {"effort": "medium"}}` | - | - | - | ok, r=0, used | - | - | - |
| `anthropic/claude-sonnet-5.5` | pin-anthropic | Anthropic | `{"reasoning": {"effort": "high"}}` | - | - | - | ok, r=0, used | - | - | - |
| `anthropic/claude-sonnet-5.5` | repeat-xhigh | Amazon Bedrock | `{"reasoning": {"effort": "xhigh"}}` | ok, r=0, model calls tool | ok, r=99, used | - | ok, r=100, used | - | - | ok, r=108, used |
| `anthropic/claude-sonnet-5.5` | repeat-xhigh-pin-anthropic | Anthropic | `{"reasoning": {"effort": "xhigh"}}` | - | - | - | ok, r=99, used | - | - | - |
| `google/gemini-3.8-flash` | pin-google-vertex | Google | `{"reasoning": {"enabled": true}, "reasoning_effort": "high"}` | - | - | - | ok, r=867, used | - | - | - |
| `google/gemini-3.1-pro-preview` | pin-google-ai-studio | Google AI Studio | `{"reasoning": {"enabled": true}, "reasoning_effort": "low"}` | - | - | - | ok, r=173, used | - | - | - |
| `openai/gpt-5.6-luna` | pin-openai | OpenAI | `{"reasoning": {"effort": "medium"}}` | ok, r=9, model calls tool | ok, r=42, used | - | ok, r=49, used | - | - | ok, r=46, used |
| `deepseek/deepseek-v4.1-flash-1017` | pin-deepseek | none (OpenRouter routing error) | `{"reasoning": {"effort": "high"}}` | **ERROR 404** | - | - | **ERROR 404** | - | - | **ERROR 404** |
| `deepseek/deepseek-v4.1-flash-1017` | pin-together | Together | `{"reasoning": {"effort": "high"}}` | - | - | - | ok, r=80, used | - | - | - |
| `deepseek/deepseek-v4.1-flash-1017` | pin-deepinfra | DeepInfra | `{"reasoning": {"effort": "high"}}` | - | - | - | ok, r=57, used | - | - | - |
| `deepseek/deepseek-v4.1-flash-1017` | pin-novita | Novita | `{"reasoning": {"effort": "high"}}` | - | - | - | ok, r=68, used | - | - | - |
| `deepseek/deepseek-v4.1-flash-1017` | pin-parasail | Parasail | `{"reasoning": {"effort": "high"}}` | - | - | - | ok, r=73, used | - | - | - |
| `moonshotai/kimi-k3` | pin-moonshotai | Moonshot AI | `{"reasoning": {"effort": "low"}}` | ok, r=24, model calls tool | ok, r=139, used | - | ok, r=47, used | - | - | - |
| `anthropic/claude-opus-5.5` | pin-anthropic | Anthropic | `{"reasoning": {"effort": "xhigh"}}` | ok, r=0, model calls tool | ok, r=100, used | - | ok, r=98, used | - | - | - |

The `pin-deepseek` row is an OpenRouter routing refusal, not a provider response. The error is quoted in section 5.

### 3. Width sweep: S0, S0n and S1 on more of Kiln's reasoning models

Thinking level: Kiln's default for the model, or `medium` where the default is `none`. Kiln's own provider order.

| Model | Run | Host that served it | Reasoning params in the request body | S0 | S0n | S1 |
|---|---|---|---|---|---|---|
| `openai/gpt-5.4-mini` | sweep | Azure | `{"reasoning_effort": "medium"}` | ok, r=81, model calls tool | ok, r=109, used | ok, r=141, used |
| `openai/gpt-5-mini` | sweep | Azure | `{"reasoning_effort": "medium"}` | ok, r=64, model calls tool | ok, r=320, used | ok, r=384, used |
| `openai/gpt-oss-20b` | sweep | Parasail | `{"reasoning": {"exclude": false}}` | ok, r=722, model calls tool | ok, r=218, used | ok, r=410, used |
| `google/gemini-3-flash-preview` | sweep | Google AI Studio | `{"reasoning": {"enabled": true}, "reasoning_effort": "high"}` | ok, r=157, model calls tool | ok, r=412, used | ok, r=549, used |
| `google/gemini-3.5-flash-lite` | sweep | Google AI Studio | `{"reasoning": {"enabled": true}, "reasoning_effort": "high"}` | ok, r=91, model calls tool | ok, r=827, used | ok, r=1027, used |
| `google/gemini-2.5-flash` | sweep | Google AI Studio | `{"reasoning": {"enabled": true}}` | ok, r=268, model calls tool | ok, r=492, used | ok, r=445, used |
| `google/gemma-4-31b-it` | sweep | Parasail | `{"reasoning": {"effort": "high"}}` | ok, r=247, model calls tool | ok, r=244, used | ok, r=361, used |
| `deepseek/deepseek-v4-pro` | sweep | DeepInfra | `{"reasoning": {"effort": "high"}}` | ok, r=29, model calls tool | ok, r=420, used | ok, r=294, used |
| `deepseek/deepseek-r1-0528` | sweep | SiliconFlow | `{"reasoning": {"exclude": false}}` | **host error in body**, r=992 | - | **ERROR 502** |
| `qwen/qwen3-235b-a22b-thinking-2507` | sweep | Venice | `{"reasoning": {"exclude": false}}` | ok, r=225, model calls tool | ok, r=410, used | ok, r=1145, used |
| `minimax/minimax-m3` | sweep | CoreWeave | `{"reasoning": {"exclude": false}}` | ok, r=72, model calls tool | ok, r=3, used | ok, r=148, used |
| `z-ai/glm-5.1` | sweep | Novita | `{}` | ok, r=15, model calls tool | ok, r=216, used | ok, r=199, used |
| `x-ai/grok-4.7` | sweep | Amazon Bedrock | `{"reasoning": {"effort": "low"}}` | ok, r=32, model calls tool | ok, r=0, used, wrong answer | ok, r=0, used, wrong answer |
| `thinkingmachines/inkling-small` | sweep | DeepInfra | `{"reasoning": {"effort": "high"}}` | ok, r=7, model calls tool | ok, r=189, used | ok, r=0, used |
| `tencent/hy4` | sweep | Tencent | `{"reasoning": {"effort": "high"}}` | ok, r=262, model calls tool | ok, r=813, used | ok, r=445, used |
| `meta/muse-spark-open` | sweep | Together | `{}` | ok, r=27, model calls tool | ok, r=331, used | ok, r=521, used |
| `nvidia/nemotron-3-super-120b-a12b` | sweep | DeepInfra | `{"reasoning": {"exclude": false}}` | ok, r=35, model calls tool | ok, r=421, used | ok, r=396, used |
| `stepfun/step-3.7-flash` | sweep | Novita | `{}` | ok, r=0, model calls tool | ok, r=0, used | ok, r=0, used |
| `bytedance-seed/seed-1.6-flash` | sweep | Seed | `{}` | ok, r=167, model calls tool | ok, r=248, model calls tool | ok, r=438, model calls tool |
| `thinkingmachines/inkling` | sweep | Together | `{"reasoning": {"effort": "high"}}` | ok, r=8, model calls tool | ok, r=226, used | ok, r=182, used |
| `deepseek/deepseek-v4-flash-0731` | sweep | Parasail | `{"reasoning": {"effort": "high"}}` | ok, r=10, model calls tool | ok, r=198, used | ok, r=266, used |
| `z-ai/glm-5.3-flashx` | sweep | Z.AI | `{"reasoning": {"effort": "high"}}` | ok, r=5, model calls tool | ok, r=70, used | ok, r=51, used |
| `z-ai/glm-5` | sweep | Novita | `{}` | ok, r=0, model calls tool | ok, r=299, used | ok, r=241, used |
| `z-ai/glm-4.7-flash` | sweep | Novita | `{}` | ok, r=38, model calls tool | ok, r=501, used | ok, r=231, used, wrong answer |
| `google/gemma-4-26b-a4b-it` | sweep | DeepInfra | `{"reasoning": {"effort": "high"}}` | ok, r=291, model calls tool | ok, r=281, used | ok, r=742, used |
| `nvidia/nemotron-3.5-lightning` | sweep | Fireworks | `{"reasoning": {"exclude": false}}` | ok, r=29, model calls tool | ok, r=393, used | ok, r=339, used |
| `nvidia/nemotron-3.5-super-vl` | sweep | Together | `{"reasoning": {"exclude": false}}` | ok, r=34, model calls tool | ok, r=398, used | ok, r=444, used |
| `nvidia/nemotron-3-ultra-550b-a55b` | sweep | DeepInfra | `{"reasoning": {"exclude": false}}` | ok, r=55, model calls tool | ok, r=399, used | ok, r=222, used |
| `minimax/minimax-m2.7` | sweep | GMICloud | `{"reasoning": {"exclude": false}}` | ok, r=13, model calls tool | ok, r=503, used | ok, r=185, used |
| `qwen/qwen3-30b-a3b` | sweep | none (OpenRouter routing error) | `{"reasoning": {"exclude": false}}` | **ERROR 404** | - | **ERROR 404** |
| `bytedance-seed/seed-1.6` | sweep | Seed | `{}` | ok, r=88, model calls tool | ok, r=616, used | ok, r=194, used |
| `google/gemini-3.7-flash` | sweep | Google AI Studio | `{"reasoning": {"enabled": true}, "reasoning_effort": "medium"}` | ok, r=55, model calls tool | ok, r=395, used | ok, r=458, used |
| `google/gemini-3.6-flash` | sweep | Google AI Studio | `{"reasoning": {"enabled": true}, "reasoning_effort": "high"}` | ok, r=91, model calls tool | ok, r=1020, used | ok, r=692, used |
| `google/gemini-3.1-flash-lite` | sweep | Google AI Studio | `{"reasoning": {"enabled": true}, "reasoning_effort": "high"}` | ok, r=365, model calls tool | ok, r=281, used | ok, r=695, used |
| `openai/gpt-6.1-terra` | sweep | Azure | `{"reasoning": {"effort": "medium"}}` | ok, r=0, model calls tool | ok, r=23, used | ok, r=27, used |
| `sakana/fugu-max` | sweep | Sakana AI | `{"reasoning": {"effort": "xhigh"}}` | ok, r=0, model calls tool | ok, r=102, used | ok, r=152, used |
| `x-ai/grok-4.5` | sweep | xAI | `{"reasoning": {"effort": "low"}}` | ok, r=25, model calls tool | ok, r=279, used | ok, r=132, used |
| `moonshotai/kimi-k3.1-pro` | sweep | Parasail | `{"reasoning": {"effort": "high"}}` | ok, r=21, model calls tool | ok, r=171, used | ok, r=199, used |
| `anthropic/claude-sonnet-5` | sweep | Amazon Bedrock | `{"reasoning": {"effort": "medium"}}` | ok, r=0, model calls tool | ok, r=117, used | ok, r=146, used |
| `anthropic/claude-sonnet-4.6` | sweep | Amazon Bedrock | `{"reasoning": {"effort": "medium"}}` | ok, r=23, model calls tool | ok, r=228, used | ok, r=223, used |

Notes on this table:

- `thinkingmachines/inkling-small`: S1 returned 0 reasoning tokens while the natural flow returned 189. See section 8.
- `x-ai/grok-4.7` was served by Amazon Bedrock and returned 0 reasoning tokens and a wrong answer in both the natural flow and S1.
- `stepfun/step-3.7-flash` returned 0 reasoning tokens in all three calls. Kiln sends no reasoning parameter for it.
- `z-ai/glm-4.7-flash` gave a wrong answer in S1 with 231 reasoning tokens.
- `bytedance-seed/seed-1.6-flash` called the tool again in both S0n and S1.
- `deepseek/deepseek-r1-0528`: in S0 the host returned HTTP 200 with `finish_reason: "error"` inside the body, then 502 on S1. A repeat gave 503 on both.
- `qwen/qwen3-30b-a3b`: OpenRouter routing refusal on both calls.

### 4. Workarounds and side probes

Run names, in the order of the table:

- `forced-tool-choice`: `tool_choice` set to force `get_user_info`. Kiln does not send this.
- `modify-params`: `litellm.modify_params = True`.
- `forged-reasoning_content`, `forged-reasoning`, `forged-unsigned-reasoning_details`: the harness-written call also carries a made-up reasoning text in that field, with no signature.
- `forged-bogus-signature`, `bogus-signature`: the harness-written call carries a top-level `reasoning_details` entry with a made-up signature.
- `dummy-signature-skip-validator`, `dummy-signature-context-engineering`: the harness-written call carries `reasoning_details: [{"type": "reasoning.encrypted", "data": <value>, "id": "call_kilnharness0001", "format": "google-gemini-v1", "index": 0}]`, with `skip_thought_signature_validator` and `context_engineering_is_the_way_to_go` as the value.
- `nested-bogus-signature`: the made-up signature sits under `provider_specific_fields.reasoning_details`, which is where LiteLLM puts reasoning details when Kiln passes a response message back inside one invoke.
- `mixed-turn`: S0 then S5. In the `xhigh` runs the model's own call from S0 carried a signed thinking block.
- `repeat`, `attribution`: repeats and controls for section 8. S6 is `[system, user "Hello", assistant "Hello! How can I help you today?" with no reasoning, user with the record inline]`.

| Model | Run | Host that served it | Scenario | Result |
|---|---|---|---|---|
| `anthropic/claude-haiku-4.5` | forced-tool-choice-pin-anthropic | Anthropic | S0 | ok, r=0, model calls tool |
| `anthropic/claude-haiku-4.5` | forced-tool-choice-pin-anthropic | Anthropic | S1 | ok, r=0, model calls tool |
| `anthropic/claude-haiku-4.5` | modify-params-pin-anthropic | Anthropic | S1 | ok, r=0, used |
| `anthropic/claude-haiku-4.5` | forged-reasoning_content-pin-anthropic | Anthropic | S1 | ok, r=0, used |
| `anthropic/claude-haiku-4.5` | forged-unsigned-reasoning_details-pin-anthropic | Anthropic | S1 | ok, r=0, used |
| `anthropic/claude-haiku-4.5` | forged-bogus-signature-pin-anthropic | Anthropic | S1 | **ERROR 400** |
| `google/gemini-3.8-flash` | dummy-signature-skip-validator | Google AI Studio | S1 | ok, r=693, used |
| `google/gemini-3.8-flash` | dummy-signature-context-engineering | Google AI Studio | S1 | ok, r=874, used |
| `google/gemini-3.8-flash` | bogus-signature | Google AI Studio | S1 | **ERROR 400** |
| `anthropic/claude-haiku-4.5` | nested-bogus-signature-pin-anthropic | Anthropic | S1 | ok, r=0, used |
| `google/gemini-3.8-flash` | nested-bogus-signature | Google AI Studio | S1 | ok, r=719, used |
| `anthropic/claude-haiku-4.5` | mixed-turn-pin-anthropic | Anthropic | S0 | ok, r=90, model calls tool |
| `anthropic/claude-haiku-4.5` | mixed-turn-pin-anthropic | Anthropic | S5 | ok, r=0, used |
| `anthropic/claude-haiku-5.5` | mixed-turn-pin-anthropic | Anthropic | S0 | ok, r=0, model calls tool |
| `anthropic/claude-haiku-5.5` | mixed-turn-pin-anthropic | Anthropic | S5 | ok, r=238, used |
| `google/gemini-3.8-flash` | mixed-turn-pin-google-ai-studio | Google AI Studio | S0 | ok, r=106, model calls tool |
| `google/gemini-3.8-flash` | mixed-turn-pin-google-ai-studio | Google AI Studio | S5 | ok, r=653, used |
| `openai/gpt-5.6-luna` | mixed-turn-pin-openai | OpenAI | S0 | ok, r=9, model calls tool |
| `openai/gpt-5.6-luna` | mixed-turn-pin-openai | OpenAI | S5 | ok, r=45, used |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | S0 | ok, r=7, model calls tool |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | S0n | ok, r=178, used |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | S1 | ok, r=0, used, wrong answer / ok, r=0, used, wrong answer |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | S4 | ok, r=0, used |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | S0c | ok, r=256, used |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | S2 | ok, r=0, used, wrong answer |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | S3 | ok, r=0, used |
| `thinkingmachines/inkling-small` | repeat | DeepInfra | W_user_after_tool | ok, r=0, used, wrong answer |
| `deepseek/deepseek-r1-0528` | repeat | SiliconFlow | S0 | **ERROR 503** |
| `deepseek/deepseek-r1-0528` | repeat | SiliconFlow | S1 | **ERROR 503** |
| `thinkingmachines/inkling-small` | forged-reasoning_content | DeepInfra | S1 | ok, r=162, used |
| `thinkingmachines/inkling-small` | forged-reasoning | DeepInfra | S1 | ok, r=217, used |
| `thinkingmachines/inkling-small` | forged-unsigned-reasoning_details | DeepInfra | S1 | ok, r=199, used |
| `thinkingmachines/inkling-small` | attribution | DeepInfra | S6 | ok, r=0, model calls tool / ok, r=0, model calls tool |
| `anthropic/claude-haiku-5.5` | mixed-turn-xhigh-pin-anthropic | Anthropic | S0 | ok, r=22, model calls tool / ok, r=21, model calls tool / ok, r=22, model calls tool |
| `anthropic/claude-haiku-5.5` | mixed-turn-xhigh-pin-anthropic | Anthropic | S5 | ok, r=182, used / ok, r=174, used / ok, r=197, used |

Layer 1 totals: 282 calls, summed `usage.cost` $0.4012.

### 5. Errors, verbatim

The OpenRouter account id in the `user_id` field is replaced with `[redacted]`. Nothing else is changed.

**No error occurred in any S1, S3, S4, S5 or user-after-tool call that reached a model host**, apart from the SiliconFlow outage in (d).

(a) `anthropic/claude-haiku-4.5`, pinned to Anthropic, S1 with a made-up signature in top-level `reasoning_details`. HTTP 400:

```
litellm.BadRequestError: OpenrouterException - {"error":{"message":"Provider returned error","code":400,"metadata":{"raw":"{\"type\":\"error\",\"error\":{\"type\":\"invalid_request_error\",\"message\":\"messages.1.content.0: Invalid `signature` in `thinking` block\"},\"request_id\":\"req_011CgtV4zqF49d6gmJzu3kZ7\"}","provider_name":"Anthropic","is_byok":false}},"user_id":"[redacted]"}
```

(b) `google/gemini-3.8-flash`, pinned to Google AI Studio, S1 with a made-up signature in top-level `reasoning_details`. HTTP 400:

```
litellm.BadRequestError: OpenrouterException - {"error":{"message":"Provider returned error","code":400,"metadata":{"raw":"Gemini models require OpenRouter reasoning details to be preserved in each request. Please refer to our docs: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens#preserving-reasoning-blocks. Upstream error: {\n  \"error\": {\n    \"code\": 400,\n    \"message\": \"Corrupted thought signature.\",\n    \"status\": \"INVALID_ARGUMENT\"\n  }\n}\n","provider_name":"Google AI Studio","is_byok":false,"provider_error_code":"400"}},"user_id":"[redacted]"}
```

The same request with no `reasoning_details` at all (plain S1) succeeded. So did the two placeholder values.

(c) `deepseek/deepseek-v4.1-flash-1017`, pinned to the first-party `deepseek` endpoint, S0, S1 and S4 alike. HTTP 404 from OpenRouter's router. No model host was called:

```
litellm.NotFoundError: NotFoundError: OpenrouterException - {"error":{"message":"No endpoints found for deepseek/deepseek-v4.1-flash-1017. Every candidate endpoint was removed during routing: Filter by Tier Endpoint Rows removed particle-ai/us/flex, deepinfra/fp8/flex, ionstream/flex (Excluded tier endpoint rows the request did not opt into); Filter by Guardrails removed deepseek (Paid model training violation (account settings)); Filter by Fallback removed relace/fp4, morph/fp8, wafer/us, primeintellect, particle-ai/us, open-inference/fp4, wafer/mxfp4, inference-net/us, inference-net/fp8, deepinfra/fp8, cloudflare, sail-research/fp4/us, streamlake/fp8, river, decart/fp8, stepfun/fp8, deepinfra/fp8/priority, cohere/fp8, makora/fp8, sail-research/fp4, reka, ionstream, novita/fp8, modelrun/fp4, dekallm, digitalocean, gmicloud/fp8, atlas-cloud/fp8, phala, alibaba, primalabs, modal, crusoe/fp8, siliconflow/fp8, coreweave/fp8, near-ai, venice/fp8, mistral/fp8, nebius/fp8, together, fireworks, baseten, parasail/fp8, fireworks/us, baseten/fast, fireworks/spot, baidu/fp8.","code":404,"metadata":{"routing_funnel":[{"step":"Initial Endpoints","endpoint_count":51},{"step":"Filter by Tier Endpoint Rows","endpoint_count":48,"reason":"Excluded tier endpoint rows the request did not opt into"},{"step":"Filter by Guardrails","endpoint_count":47,"reason":"Paid model training violation (account settings)"},{"step":"Apply Status Sorting","endpoint_count":47},{"step":"Filter by Fallback","endpoint_count":0}],"failed_routing_step":"Filter by Fallback"}},"user_id":"[redacted]"}
```

`qwen/qwen3-30b-a3b` failed in the same way on S0 and S1, with the message `All providers have been ignored. To change your default ignored providers, visit: https://openrouter.ai/settings/privacy`.

(d) `deepseek/deepseek-r1-0528`, host SiliconFlow. S0 (the control) returned HTTP 200 with this inside the choice: `"finish_reason": "error"`, `"error": {"code": 502, "message": "JSON error injected into SSE stream", "metadata": {"error_type": "provider_unavailable"}}`. S1 returned HTTP 502:

```
litellm.APIError: APIError: OpenrouterException - {"error":{"message":"Provider returned error","code":502,"metadata":{"raw":"{\"code\":50507,\"message\":\"Request failed: Unknown error.\",\"data\":null}","provider_name":"SiliconFlow","is_byok":false}},"user_id":"[redacted]"}
```

The repeat returned HTTP 503 on S0 and on S1:

```
litellm.ServiceUnavailableError: ServiceUnavailableError: OpenrouterException - {"error":{"message":"Provider returned error","code":503,"metadata":{"raw":"{\"code\":50508,\"message\":\"System is too busy now. Please try again later.\",\"data\":null}","provider_name":"SiliconFlow","is_byok":false}},"user_id":"[redacted]"}
```

### 6. What was actually sent upstream

**LiteLLM to OpenRouter (observed, from the captured HTTP body).**

The S1 body for `anthropic/claude-haiku-4.5`, with long strings shortened:

```json
{
  "model": "anthropic/claude-haiku-4.5",
  "messages": [
    {"role": "system", "content": "You are the support assistant for Acme Cloud. ..."},
    {"role": "user", "content": "Given my plan and my city, work out step by step ..."},
    {"role": "assistant", "tool_calls": [{"id": "call_kilnharness0001", "type": "function", "function": {"name": "get_user_info", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_kilnharness0001", "content": "{\"name\": \"Dana Okafor\", \"plan\": \"enterprise\", \"city\": \"Lisbon\", \"account_id\": \"A-7731\"}"}
  ],
  "temperature": 1.0,
  "top_p": 1.0,
  "max_tokens": 2500,
  "tools": [{"type": "function", "function": {"name": "get_user_info", "description": "...", "parameters": {"type": "object", "properties": {}}, "strict": false}}],
  "tool_choice": "auto",
  "reasoning": {"effort": "medium"},
  "usage": {"include": true},
  "provider": {"order": ["fireworks", "parasail", "together", "deepinfra", "novita", "groq", "amazon-bedrock", "azure", "nebius"]}
}
```

Across all 283 Layer 1 calls (the 282 in the tables and one smoke test):

- The reasoning parameters in the body equalled the ones in Kiln's kwargs, with two exceptions. For `google/gemini-4-argon` Kiln passed `reasoning_effort: "low"` and `reasoning: {"enabled": true}`, and the body carried only `reasoning: {"enabled": true}`. For `meta/muse-spark-open` Kiln passed `reasoning_effort: "medium"` and the body carried no reasoning parameter. Both happened in every call for those models, including S0, so they do not depend on the message history. For the Gemini 3.x and GPT-5 models `reasoning_effort` was in the body.
- The only change LiteLLM made to any message was to remove `"content": null` from assistant tool-call messages. Extra keys on the harness-written message (`reasoning_content`, `reasoning`, `reasoning_details`, `provider_specific_fields`) went out unchanged.
- With `litellm.modify_params = True` the S1 body was identical to the body without it.
- LiteLLM logged nothing at WARNING or above in any call.
- Each call was one HTTP request. LiteLLM did not retry.

**OpenRouter to the model host (not visible; what the responses show).**

- A top-level `reasoning_details` entry with a signature is forwarded: the made-up one drew an upstream 400 from Anthropic that names a `thinking` block at `messages.1.content.0`, and one from Google AI Studio (section 5).
- Reasoning text without a signature (`reasoning_content`, or an unsigned `reasoning_details` entry) on the harness-written call drew no error from Anthropic.
- A Gemini function call with no signature at all drew no error, on AI Studio and on Vertex.
- The same made-up signatures placed under `provider_specific_fields.reasoning_details` drew no error from Anthropic or Google.
- `anthropic/claude-haiku-4.5` on Anthropic with reasoning on and a forced `tool_choice` returned HTTP 200 with 0 reasoning tokens, in S0 and in S1.
- A harness-written call placed before a model-made call that carries a signed thinking block (S5, Claude Haiku 5.5 on Anthropic at `xhigh`, three runs) drew no error and returned reasoning each time.

### 7. Layer 2: through Kiln's adapter

| Model | Flow | Result | Kiln-side error | Reasoning tokens per LLM call | Chars in Kiln `intermediate_outputs["reasoning"]` | Answer used tool result |
|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | natural_first | ok, tool call pending | none | [0] | 0 | - |
| `anthropic/claude-haiku-5.5` | natural_resume | ok | none | [142] | 288 | yes |
| `anthropic/claude-haiku-5.5` | harness_resume | ok | none | [174] | 283 | yes |
| `anthropic/claude-haiku-5.5` | harness_premessage | ok | none | [257] | 317 | yes |
| `anthropic/claude-haiku-5.5` | natural_inloop | ok | none | [0, 160] | 357 | yes |
| `anthropic/claude-haiku-4.5` | natural_first | ok, tool call pending | none | [69] | 0 | - |
| `anthropic/claude-haiku-4.5` | natural_resume | ok | none | [0] | 0 | yes |
| `anthropic/claude-haiku-4.5` | harness_resume | ok | none | [0] | 0 | yes |
| `anthropic/claude-haiku-4.5` | harness_premessage | ok | none | [485] | 1781 | yes |
| `anthropic/claude-haiku-4.5` | natural_inloop | ok | none | [130, 0] | 0 | yes |
| `google/gemini-3.8-flash` | natural_first | ok, tool call pending | none | [67] | 0 | - |
| `google/gemini-3.8-flash` | natural_resume | ok | none | [825] | 1203 | yes |
| `google/gemini-3.8-flash` | harness_resume | ok | none | [770] | 970 | yes |
| `google/gemini-3.8-flash` | harness_premessage | ok | none | [580] | 700 | yes |
| `google/gemini-3.8-flash` | natural_inloop | ok | none | [61, 676] | 631 | yes |
| `openai/gpt-5.6-luna` | natural_first | ok, tool call pending | none | [9] | 0 | - |
| `openai/gpt-5.6-luna` | natural_resume | ok | none | [52] | 429 | yes |
| `openai/gpt-5.6-luna` | harness_resume | ok | none | [44] | 404 | yes |
| `openai/gpt-5.6-luna` | harness_premessage | ok | none | [48] | 476 | yes |
| `openai/gpt-5.6-luna` | natural_inloop | ok | none | [9, 49] | 456 | yes |
| `moonshotai/kimi-k2-thinking` | natural_first | ok, tool call pending | none | [53] | 0 | - |
| `moonshotai/kimi-k2-thinking` | natural_resume | ok | none | [215] | 794 | yes |
| `moonshotai/kimi-k2-thinking` | harness_resume | ok | none | [309] | 1083 | yes |
| `moonshotai/kimi-k2-thinking` | harness_premessage | ok | none | [344] | 1207 | yes |
| `moonshotai/kimi-k2-thinking` | natural_inloop | ok | none | [61, 276] | 1007 | yes |
| `deepseek/deepseek-v4.1-flash-1017` | natural_first | ok, tool call pending | none | [0] | 0 | - |
| `deepseek/deepseek-v4.1-flash-1017` | natural_resume | ok | none | [69] | 261 | yes |
| `deepseek/deepseek-v4.1-flash-1017` | harness_resume | ok | none | [83] | 315 | yes |
| `deepseek/deepseek-v4.1-flash-1017` | harness_premessage | ok | none | [128] | 512 | yes |
| `deepseek/deepseek-v4.1-flash-1017` | natural_inloop | ok | none | [0, 76] | 294 | yes |
| `anthropic/claude-haiku-4.5` | harness_resume_stream | ok | none | not captured (streamed) | 0 | yes |
| `anthropic/claude-haiku-5.5` | harness_resume_stream | ok | none | not captured (streamed) | 266 | yes |
| `google/gemini-3.8-flash` | harness_resume_stream | ok | none | not captured (streamed) | 1037 | yes |
| `openai/gpt-5.6-luna` | harness_resume_stream | ok | none | not captured (streamed) | 368 | yes |
| `thinkingmachines/inkling-small` | natural_first | ok, tool call pending | none | [18] | 0 | - |
| `thinkingmachines/inkling-small` | natural_resume | ok | none | [239] | 956 | yes |
| `thinkingmachines/inkling-small` | harness_resume | ok | none | [0] | 0 | yes |
| `thinkingmachines/inkling-small` | harness_premessage | ok | none | [0] | 0 | yes, wrong answer |
| `thinkingmachines/inkling-small` | natural_inloop | ok | none | [8, 115] | 459 | yes |

Layer 2 totals: 39 invokes, 46 LLM calls, summed `usage.cost` of the non-streamed calls $0.0382.

Observed:

- Every flow returned a `TaskRun`. No exception was raised by Kiln or LiteLLM in any of the 39 invokes.
- `harness_resume` and `harness_premessage` produced a final answer for all 7 models. For 6 of them Kiln recorded reasoning in `intermediate_outputs["reasoning"]` in at least one of the two flows. `anthropic/claude-haiku-4.5` returned no reasoning in `harness_resume`, as in its `natural_resume`, and did in `harness_premessage`. `thinkingmachines/inkling-small` returned none in either harness flow (section 8).
- The returned trace keeps the harness-written message as given (`role`, `content`, `tool_calls`), followed by the tool message and the model's answer.
- The streaming entry point (`invoke_openai_stream`) gave the same outcome for the 4 models tried.

The check in `base_adapter.py` that raises `"Reasoning is required for this model, but no reasoning was returned."` did not fire in any flow. From the code (lines 303 to 324 at the probed commit): it applies only when `provider.reasoning_capable` is true, and it is skipped when the trace contains any message with role `tool`. Of the 7 models, only `moonshotai/kimi-k2-thinking` has `reasoning_capable=True` on its openrouter entry, and it returned reasoning anyway. Both harness flows always have a tool message in the trace. The probe did not produce a run where a `reasoning_capable` model returned no reasoning, so the skip itself was not exercised.

**What Kiln put on the wire for a model-made tool call (observed, from the captured bodies).**

In `natural_resume` the trace Kiln stored after `natural_first` is sent back. Its assistant message has `content`, `tool_calls` and, when LiteLLM surfaced reasoning text, `reasoning_content`. The message that went out:

| Model | What the first response carried | Assistant tool-call message sent in `natural_resume` |
|---|---|---|
| `anthropic/claude-haiku-4.5` | One `reasoning.text` entry, 249 chars, with a signature | `{"role": "assistant", "reasoning_content": "<249 chars>", "tool_calls": [...]}`. No signature. |
| `openai/gpt-5.6-luna` | One `reasoning.summary` entry, 360 chars, and one `reasoning.encrypted` entry, 3641 chars | `{"role": "assistant", "reasoning_content": "<360 chars>", "tool_calls": [...]}`. No encrypted entry. |
| `google/gemini-3.8-flash` | One `reasoning.encrypted` entry, 528 chars | `{"role": "assistant", "tool_calls": [...]}`. Nothing else. |
| `anthropic/claude-haiku-5.5` | No reasoning in this run | `{"role": "assistant", "tool_calls": [...]}` |

In `natural_inloop` Kiln passes LiteLLM's own response message object back. The message that went out had `reasoning_content` at the top level (where the provider returned text) and the provider's `reasoning_details`, with signatures and encrypted data, nested under `provider_specific_fields`. For `anthropic/claude-haiku-4.5`:

```json
{"role": "assistant",
 "tool_calls": [{"index": 0, "function": {"arguments": "{}", "name": "get_user_info"}, "id": "toolu_bdrk_...", "type": "function"}],
 "reasoning_content": "<507 chars>",
 "provider_specific_fields": {
   "refusal": null,
   "reasoning": "<507 chars>",
   "reasoning_details": [{"type": "reasoning.text", "text": "<507 chars>", "format": "anthropic-claude-v1", "index": 0, "signature": "<1128 chars>"}]}}
```

OpenRouter's own responses have `reasoning_details` at the top level of the message. The side probe in section 4 put a made-up signature in each place: at the top level it drew a 400 from Anthropic and from Google, and under `provider_specific_fields` it drew none.

All of these natural flows returned an answer that used the tool result.

### 8. The one model that lost reasoning: `thinkingmachines/inkling-small`

Kiln lists it as an openrouter model with thinking levels `none` to `max`, default `high`. OpenRouter has one endpoint for it, DeepInfra. All calls below used `reasoning: {"effort": "high"}`, except the S2 row.

| History before the call | Calls | Reasoning tokens | Answers |
|---|---|---|---|
| No assistant message (S0c) | 1 | 256 | correct |
| Model's own call passed back with its reasoning (S0n twice, Layer 2 `natural_resume`, Layer 2 `natural_inloop`) | 4 | 189, 178, 239, 115 | 4 correct |
| Harness-written call with no reasoning, model called right after the tool result (S1 three times, Layer 2 `harness_resume`, user-after-tool variant) | 5 | 0, 0, 0, 0, 0 | 2 correct, 3 wrong |
| Harness-written call with no reasoning, earlier in the history (S3, S4, Layer 2 `harness_premessage`) | 3 | 0, 0, 0 | 2 correct, 1 wrong |
| Harness-written call that also carries made-up reasoning text, as `reasoning_content`, as `reasoning`, or as an unsigned `reasoning_details` entry | 3 | 162, 217, 199 | 3 correct |
| Harness-written call, reasoning off (S2) | 1 | 0 | wrong |
| An earlier plain assistant message with no reasoning and no tool call (S6) | 2 | 0, 0 | the model called the tool both times |

The wrong answers all say "Silver" and "Borealis". The larger sibling `thinkingmachines/inkling` (host Together) returned 182 reasoning tokens in S1. No other model in the probe showed this pattern.

## Observed and inferred, kept apart

Observed:

- Through OpenRouter, a history with a harness-written tool call that has no reasoning attached was accepted by every model host that was reached: Amazon Bedrock, Anthropic, Azure, Google AI Studio, Google Vertex, OpenAI, xAI, Moonshot AI, Fireworks, Together, DeepInfra, Novita, Parasail, Z.AI, Tencent, Seed, Venice, CoreWeave, GMICloud and Sakana AI.
- The position of the call did not change that: in the current turn (S1), in an earlier turn (S3), before the first user message (S4), or before a signed model-made call in the same turn (S5).
- For `anthropic/claude-haiku-4.5` the call right after a tool result returned 0 reasoning tokens whether the preceding tool call was harness-written or the model's own with its signed thinking passed back.
- For Claude Haiku 5.5, Sonnet 5.5, Sonnet 5, Sonnet 4.6 and Opus 5.5, and for the Gemini 2.5 and 3.x, OpenAI, DeepSeek, Kimi, GLM, Grok 4.3 and 4.5, Qwen, MiniMax, Nemotron, Gemma, Hunyuan, Muse Spark, Seed 1.6, Inkling and Fugu models tested, the call after a harness-written call returned reasoning tokens, as the call after the model's own call did.
- `thinkingmachines/inkling-small` returned no reasoning after any assistant message that had no reasoning attached, and did when reasoning text was attached.
- LiteLLM 1.102.0 on the `openrouter/` route did not alter the reasoning parameters because of the message history, with or without `modify_params`.
- Kiln's resume path and its in-loop tool path both worked with these models. The resume path sends no signature. The in-loop path sends the signature nested under `provider_specific_fields`.

Inferred, not observed:

- OpenRouter, or the host behind it, supplies something for a Gemini function call that has no thought signature. The basis: a corrupted signature is rejected by Google, a missing one is not, and `docs_probe.md` reports that Google's own API rejects a missing one.
- For `anthropic/claude-haiku-4.5`, either OpenRouter or the Anthropic-side API turns thinking off for the S1 request, or the request is accepted as it is and the model does not think after a tool result. The basis: no 400 on four hosts, 0 reasoning tokens, and HTTP 200 with 0 reasoning tokens when `tool_choice` was forced. Which of these happens cannot be told from outside. The natural flow gives the same 0.
- OpenRouter ignores `provider_specific_fields` on input messages. The basis: the made-up signatures placed there drew no error. If so, a model-made tool call that Kiln passes back inside one invoke reaches the model host without its signature, as in the resume path.
- OpenRouter drops reasoning text that has no signature before calling Anthropic. The basis: such text drew no error, and a made-up signature did.
- `google/gemini-4-argon` and `meta/muse-spark-open` lost `reasoning_effort` because LiteLLM, called with `drop_params=True`, removes parameters it does not know a model supports. The basis: the parameter was in the kwargs and not in the body, and it survived for other models. LiteLLM's code path was not traced.
- The cause of the `inkling-small` result is not known. The S6 control is consistent with the model following the pattern of earlier assistant messages, but in S6 the model made a tool call, and its tool calls carried few reasoning tokens in every run (7 to 18).

Not established by this probe:

- Whether Anthropic's, Google's, DeepSeek's or Moonshot's own API returns the documented errors for this history when called without OpenRouter in between.
- Whether the same holds on Kiln's native `anthropic`, `gemini_api`, `vertex`, `openai` or `amazon_bedrock` providers.

## Spend

| | USD |
|---|---|
| `usage` on `GET /api/v1/key` before the probe | 0.022359 |
| `usage` on `GET /api/v1/key` after the probe | 0.468127 |
| Spent by the probe | 0.4458 |
| Sum of `usage.cost` over the 283 captured Layer 1 calls | 0.4012 |
| Sum of `usage.cost` over the 42 captured Layer 2 LLM calls | 0.0382 |
| 4 streamed Layer 2 calls, cost not captured | the remainder, about 0.006 |

The key's limit is 4.00 USD. 3.554 USD remained after the probe.

## Appendix: probe scripts

The scripts ran from the Kiln repo root with `uv run python <script>`. They lived outside the repo. The key is read from the `OPENROUTER_QA_KEY` environment variable and copied in process to `OPENROUTER_API_KEY`, the variable Kiln's config reads. It is never printed or written to disk.

### `probe_common.py`

```python
"""Shared pieces for the harness-injected tool call probe.

Layer 1 (layer1.py) makes raw `litellm.acompletion` calls with hand-built message
histories. The non-message parameters come from Kiln's own
`LiteLlmAdapter.build_completion_kwargs`, so each request carries exactly the
reasoning parameters Kiln would send for that model on its openrouter provider.

Layer 2 (layer2.py) runs the same case through `adapter.invoke`.

The OpenRouter key is read from the OPENROUTER_QA_KEY environment variable and is
only ever placed in process memory. It is never printed or written to disk.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

OUT_DIR = Path(__file__).parent / "out"
KEY_ENV = "OPENROUTER_QA_KEY"
MAX_TOKENS = 2500

TOOL_NAME = "get_user_info"
TOOL_DESCRIPTION = (
    "Look up the account record of the signed-in user: name, plan, city and "
    "account_id. Takes no arguments."
)
TOOL_RESULT = json.dumps(
    {
        "name": "Dana Okafor",
        "plan": "enterprise",
        "city": "Lisbon",
        "account_id": "A-7731",
    }
)
HARNESS_CALL_ID = "call_kilnharness0001"

SYSTEM = (
    "You are the support assistant for Acme Cloud. You can look up the signed-in "
    "user's account with the get_user_info tool. Keep the final answer short."
)

# Correct answer with the tool result above: enterprise + Lisbon (an EU capital)
# gives Gold; the account id ends in an odd digit, but Lisbon has exactly six
# letters, so the downgrade does not apply. Gold, hub Aurora, user Dana.
QUESTION = (
    "Given my plan and my city, work out step by step which of these three "
    "support tiers applies to me, then tell me the tier and the name of my "
    "support hub, and address me by my first name.\n"
    "Rules:\n"
    "1) Gold: enterprise-plan customers located in the capital city of an EU "
    "member state.\n"
    "2) Silver: enterprise-plan customers anywhere else, and pro-plan customers "
    "located in the capital city of an EU member state.\n"
    "3) Bronze: everyone else.\n"
    "Exception: a customer whose account id ends in an odd digit is moved one "
    "tier down (Gold to Silver, Silver to Bronze), unless the name of their city "
    "has exactly six letters.\n"
    "Support hubs: Gold is 'Aurora', Silver is 'Borealis', Bronze is 'Cirrus'."
)
FIRST_ANSWER = "Dana, your support tier is Gold and your support hub is Aurora."
# Correct answer: pro + Paris (EU capital) gives Silver; the account id (only
# present in the tool result) ends in 1 and Paris has five letters, so one tier
# down: Bronze, hub Cirrus.
FOLLOW_UP = (
    "Thanks. Now suppose I downgrade to the pro plan and move to Paris. Work out "
    "step by step which tier and which support hub would apply to me then."
)
PLACEHOLDER_USER = "(session started)"


def load_key_into_process() -> str:
    """Kiln reads its OpenRouter key from the OPENROUTER_API_KEY env var, so the QA
    key is copied to that name for this process only."""
    key = os.environ.get(KEY_ENV)
    if not key:
        raise SystemExit(f"{KEY_ENV} is not set")
    os.environ["OPENROUTER_API_KEY"] = key
    return key


def scrub(value: Any, key: str) -> Any:
    """Defence in depth: replace the key if it ever shows up in something we store."""
    text = json.dumps(value, default=str)
    if key in text:
        text = text.replace(key, "[REDACTED]")
    return json.loads(text)


# --------------------------------------------------------------------------
# HTTP capture: the literal JSON body LiteLLM sends to OpenRouter, and the raw
# JSON OpenRouter returns. Headers are never recorded.
# --------------------------------------------------------------------------

CAPTURED: list[dict[str, Any]] = []
_orig_send = httpx.AsyncClient.send


async def _capturing_send(self: httpx.AsyncClient, request: httpx.Request, *a, **kw):
    record: dict[str, Any] = {"url": str(request.url), "method": request.method}
    try:
        record["request_json"] = json.loads(request.content.decode("utf-8"))
    except Exception:
        record["request_json"] = None
    response = await _orig_send(self, request, *a, **kw)
    record["status"] = response.status_code
    try:
        await response.aread()
        record["response_json"] = response.json()
    except Exception:
        try:
            record["response_text"] = response.text[:4000]
        except Exception:
            record["response_text"] = None
    if "openrouter.ai" in record["url"]:
        CAPTURED.append(record)
    return response


def install_http_capture() -> None:
    httpx.AsyncClient.send = _capturing_send  # type: ignore[method-assign]


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.name}:{record.levelname}:{record.getMessage()}")


LITELLM_LOG = _ListHandler()


def install_litellm_log_capture() -> None:
    """Collect LiteLLM warnings (for example "Dropping 'thinking' param ...")."""
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logging.getLogger(name).addHandler(LITELLM_LOG)


# --------------------------------------------------------------------------
# Kiln lookups
# --------------------------------------------------------------------------


def kiln_model_for_slug(slug: str):
    from kiln_ai.adapters.ml_model_list import ModelProviderName, built_in_models

    for model in built_in_models:
        for provider in model.providers:
            if (
                provider.name == ModelProviderName.openrouter
                and provider.model_id == slug
            ):
                return model.name, provider
    raise ValueError(f"{slug} is not an openrouter model in Kiln's model list")


def make_task():
    from kiln_ai import datamodel

    return datamodel.Task(name="harness tool call probe", instruction=SYSTEM)


def make_tool():
    from kiln_ai.datamodel.tool_id import build_kiln_unmanaged_tool_id
    from kiln_ai.tools.base_tool import UnmanagedKilnTool

    return UnmanagedKilnTool(
        tool_id=build_kiln_unmanaged_tool_id(TOOL_NAME),
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        parameters_schema={"type": "object", "properties": {}},
    )


def make_adapter(slug: str, thinking_level: str | None, return_on_tool_call: bool):
    """A Kiln adapter on the openrouter provider. `thinking_level=None` leaves the
    field unset, so Kiln falls back to the provider's default level."""
    from kiln_ai.adapters.adapter_registry import adapter_for_task
    from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
    from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

    model_name, _ = kiln_model_for_slug(slug)
    fields: dict[str, Any] = {
        "model_name": model_name,
        "model_provider_name": "openrouter",
        "prompt_id": "simple_prompt_builder",
        "structured_output_mode": "default",
        "temperature": 1,
        "top_p": 1,
    }
    if thinking_level is not None:
        fields["thinking_level"] = thinking_level
    return adapter_for_task(
        make_task(),
        KilnAgentRunConfigProperties(**fields),
        AdapterConfig(
            allow_saving=False,
            return_on_tool_call=return_on_tool_call,
            unmanaged_tools=[make_tool()],
        ),
    )


# --------------------------------------------------------------------------
# Message histories
# --------------------------------------------------------------------------


def harness_call(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """The assistant message the harness writes. No reasoning fields by default."""
    message: dict[str, Any] = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": HARNESS_CALL_ID,
                "type": "function",
                "function": {"name": TOOL_NAME, "arguments": "{}"},
            }
        ],
    }
    if extra:
        message.update(copy.deepcopy(extra))
    return message


def tool_result() -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": HARNESS_CALL_ID, "content": TOOL_RESULT}


def natural_call_from_raw(raw_message: dict[str, Any]) -> dict[str, Any]:
    """The model's own tool-call message as OpenRouter returned it (including any
    `reasoning` / `reasoning_details`), minus keys whose value is null."""
    return {k: v for k, v in raw_message.items() if v is not None}


def scenario_messages(
    scenario: str,
    call_extra: dict[str, Any] | None = None,
    natural_call: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    system = {"role": "system", "content": SYSTEM}
    user = {"role": "user", "content": QUESTION}
    if scenario in ("S0",):
        return [system, user]
    if scenario == "S0c":
        # Reasoning control with no tool call needed: the record is in the question.
        return [
            system,
            {
                "role": "user",
                "content": f"My account record is {TOOL_RESULT}.\n\n{QUESTION}",
            },
        ]
    if scenario == "S0n":
        # Natural flow control: the model's own tool call from S0, passed back as
        # OpenRouter returned it, followed by the tool result.
        if natural_call is None:
            raise ValueError("S0n needs the model-made tool call from S0")
        call_id = natural_call["tool_calls"][0]["id"]
        return [
            system,
            user,
            natural_call,
            {"role": "tool", "tool_call_id": call_id, "content": TOOL_RESULT},
        ]
    if scenario == "S6":
        # Attribution control, no tool call anywhere: an earlier plain-text assistant
        # message that has no reasoning attached, then the question with the record
        # inline.
        return [
            system,
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hello! How can I help you today?"},
            {
                "role": "user",
                "content": f"My account record is {TOOL_RESULT}.\n\n{QUESTION}",
            },
        ]
    if scenario == "S5":
        # Mixed turn: the harness-written call (no reasoning) and then the model's
        # own call from S0 with its real reasoning details, both in one turn.
        if natural_call is None:
            raise ValueError("S5 needs the model-made tool call from S0")
        call_id = natural_call["tool_calls"][0]["id"]
        return [
            system,
            user,
            harness_call(call_extra),
            tool_result(),
            natural_call,
            {"role": "tool", "tool_call_id": call_id, "content": TOOL_RESULT},
        ]
    if scenario in ("S1", "S2"):
        return [system, user, harness_call(call_extra), tool_result()]
    if scenario == "S3":
        return [
            system,
            user,
            harness_call(call_extra),
            tool_result(),
            {"role": "assistant", "content": FIRST_ANSWER},
            {"role": "user", "content": FOLLOW_UP},
        ]
    if scenario == "S4":
        return [system, harness_call(call_extra), tool_result(), user]
    if scenario == "S4b":
        return [
            system,
            {"role": "user", "content": PLACEHOLDER_USER},
            harness_call(call_extra),
            tool_result(),
            user,
        ]
    if scenario == "W_user_after_tool":
        # Workaround candidate: close the tool turn with a user text message.
        return [
            system,
            user,
            harness_call(call_extra),
            tool_result(),
            {"role": "user", "content": "Go ahead and answer my question."},
        ]
    raise ValueError(f"unknown scenario {scenario}")


# --------------------------------------------------------------------------
# Reading results
# --------------------------------------------------------------------------


def summarize_raw_response(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Pull the fields we care about out of OpenRouter's raw JSON response."""
    if not isinstance(raw, dict):
        return {}
    if "error" in raw and "choices" not in raw:
        return {"raw_error": raw["error"]}
    choice = (raw.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = raw.get("usage") or {}
    details = message.get("reasoning_details") or []
    detail_summary = []
    for d in details:
        if not isinstance(d, dict):
            continue
        detail_summary.append(
            {
                "type": d.get("type"),
                "format": d.get("format"),
                "id": d.get("id"),
                "text_len": len(d.get("text") or d.get("summary") or ""),
                "data_len": len(d.get("data") or ""),
                "has_signature": bool(d.get("signature")),
            }
        )
    reasoning_text = message.get("reasoning") or ""
    content = message.get("content") or ""
    return {
        "provider": raw.get("provider"),
        "model": raw.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "native_finish_reason": choice.get("native_finish_reason"),
        "choice_error": choice.get("error"),
        "content": content,
        "tool_calls": [
            {
                "id": tc.get("id"),
                "name": (tc.get("function") or {}).get("name"),
                "arguments": (tc.get("function") or {}).get("arguments"),
            }
            for tc in (message.get("tool_calls") or [])
        ],
        "reasoning_text_len": len(reasoning_text),
        "reasoning_text_head": reasoning_text[:300],
        "reasoning_details": detail_summary,
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
            "reasoning_tokens"
        ),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cost": usage.get("cost"),
    }


def answer_checks(scenario: str, content: str) -> dict[str, bool]:
    """Rough literal checks for the console line. The report's tables use the
    stricter check in tabulate.answer_flags, plus a read of every flagged answer."""
    text = (content or "").lower()
    if scenario == "S3":
        return {
            "correct_tier": "bronze" in text or "cirrus" in text,
        }
    return {
        "uses_name": "dana" in text,
        "correct_tier": "gold" in text and "aurora" in text,
    }


def now_ms() -> int:
    return int(time.time() * 1000)


def append_jsonl(path: Path, record: dict[str, Any], key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(scrub(record, key), default=str) + "\n")
```

### `layer1.py`

```python
"""Layer 1: raw litellm.acompletion calls through OpenRouter.

Usage (from the Kiln repo root):
    uv run python <this file> --model anthropic/claude-haiku-5.5 --level high \
        [--scenarios S0,S0n,S0c,S1,S2,S3,S4] [--only-provider anthropic] \
        [--call-extra '{"reasoning_content": "..."}'] [--modify-params] \
        [--force-tool-choice] [--max-tokens N] [--tag note]

Scenarios (message histories are built in probe_common.scenario_messages):
  S0   [system, user], reasoning on. Does the model call the tool itself?
  S0n  S0's own tool call passed back as OpenRouter returned it, plus the result.
  S0c  [system, user with the record inline], reasoning on. Reasoning control.
  S1   [system, user, harness-written call, tool result], reasoning on.
  S2   the S1 history with reasoning off.
  S3   harness-written call in an earlier turn, then a text answer and a new
       user message.
  S4   harness-written call and result before the user's message.
  S4b  S4 with a leading placeholder user message.
  S5   harness-written call, then the model's own call from S0, in one turn.
  S6   an earlier plain assistant message with no reasoning, no tool call.
  W_user_after_tool  the S1 history plus a closing user text message.

Every call is appended as one JSON line to out/layer1.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import litellm
import probe_common as pc

REASONING_KEYS = ("reasoning", "reasoning_effort", "thinking")


async def build_kwargs(
    slug: str,
    level: str | None,
    messages: list[dict[str, Any]],
    reasoning_on: bool,
) -> tuple[dict[str, Any], str]:
    """Kiln's own completion kwargs for this model, with our messages.

    Returns the kwargs and a note on how reasoning was configured.
    """
    _, provider = pc.kiln_model_for_slug(slug)
    levels = list((provider.available_thinking_levels or {}).values())
    strip = False
    if reasoning_on:
        use_level = level
        note = f"on: thinking_level={level!r}"
    elif "none" in levels:
        use_level = "none"
        note = "off: thinking_level='none'"
    else:
        use_level = level
        strip = True
        note = "off: reasoning params omitted (Kiln lists no 'none' level)"

    adapter = pc.make_adapter(slug, use_level, return_on_tool_call=True)
    kwargs = await adapter.build_completion_kwargs(
        adapter.model_provider(), messages, None, False
    )
    if strip:
        for k in REASONING_KEYS:
            kwargs.pop(k, None)
    kwargs["max_tokens"] = pc.MAX_TOKENS
    return kwargs, note


async def run_one(
    slug: str,
    level: str | None,
    scenario: str,
    key: str,
    only_provider: str | None,
    call_extra: dict[str, Any] | None,
    tag: str,
    max_tokens: int | None,
    natural_call: dict[str, Any] | None = None,
    force_tool_choice: bool = False,
) -> dict[str, Any]:
    base_scenario = scenario
    reasoning_on = scenario != "S2"
    messages = pc.scenario_messages(base_scenario, call_extra, natural_call)
    kwargs, reasoning_note = await build_kwargs(slug, level, messages, reasoning_on)
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if force_tool_choice:
        # Not something Kiln sends. Anthropic documents that forced tool use is
        # rejected while thinking is enabled, so this shows whether thinking is
        # still enabled by the time the request reaches the model host.
        kwargs["tool_choice"] = {
            "type": "function",
            "function": {"name": pc.TOOL_NAME},
        }
    if only_provider:
        # Pin the upstream host instead of using Kiln's default provider order.
        kwargs["provider"] = {"order": [only_provider], "allow_fallbacks": False}

    visible_kwargs = {
        k: v for k, v in kwargs.items() if k not in ("api_key", "messages")
    }
    record: dict[str, Any] = {
        "ts": pc.now_ms(),
        "layer": 1,
        "model": slug,
        "scenario": scenario,
        "tag": tag,
        "reasoning_config": reasoning_note,
        "only_provider": only_provider,
        "modify_params": litellm.modify_params,
        "litellm_kwargs": visible_kwargs,
        "messages": messages,
    }

    pc.CAPTURED.clear()
    pc.LITELLM_LOG.lines.clear()
    try:
        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        record["ok"] = True
        record["litellm_message"] = {
            "content": message.content,
            "reasoning_content_len": len(
                getattr(message, "reasoning_content", None) or ""
            ),
            "has_thinking_blocks": bool(getattr(message, "thinking_blocks", None)),
            "provider_specific_fields_keys": sorted(
                (getattr(message, "provider_specific_fields", None) or {}).keys()
            ),
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "args": tc.function.arguments}
                for tc in (message.tool_calls or [])
            ],
        }
    except Exception as e:
        record["ok"] = False
        record["error_type"] = type(e).__name__
        record["error_status"] = getattr(e, "status_code", None)
        record["error_message"] = str(e)

    record["litellm_log"] = list(pc.LITELLM_LOG.lines)
    record["http"] = [
        {
            "url": c["url"],
            "status": c.get("status"),
            "request_json": c.get("request_json"),
            "response_json": c.get("response_json"),
            "response_text": c.get("response_text"),
        }
        for c in pc.CAPTURED
    ]
    last_raw = pc.CAPTURED[-1].get("response_json") if pc.CAPTURED else None
    record["summary"] = pc.summarize_raw_response(last_raw)
    record["checks"] = pc.answer_checks(
        base_scenario, record["summary"].get("content", "")
    )
    return record


def one_line(record: dict[str, Any]) -> str:
    s = record.get("summary", {})
    sent = (record.get("http") or [{}])[-1].get("request_json") or {}
    sent_reasoning = {k: sent[k] for k in REASONING_KEYS if k in sent}
    if record.get("ok"):
        details = [d["type"] for d in s.get("reasoning_details", [])]
        return (
            f"{record['model']} {record['scenario']} [{record['tag']}] OK "
            f"provider={s.get('provider')} sent={json.dumps(sent_reasoning)} "
            f"reasoning_tokens={s.get('reasoning_tokens')} "
            f"reasoning_chars={s.get('reasoning_text_len')} details={details} "
            f"tool_calls={[t['name'] for t in s.get('tool_calls', [])]} "
            f"finish={s.get('finish_reason')} checks={record['checks']} "
            f"cost={s.get('cost')}\n    answer: {(s.get('content') or '')[:220]!r}"
        )
    return (
        f"{record['model']} {record['scenario']} [{record['tag']}] ERROR "
        f"status={record.get('error_status')} sent={json.dumps(sent_reasoning)} "
        f"{record.get('error_type')}: {record.get('error_message', '')[:1500]}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--level", default=None)
    parser.add_argument("--scenarios", default="S0,S0n,S0c,S1,S2,S3,S4")
    parser.add_argument("--only-provider", default=None)
    parser.add_argument(
        "--call-extra", default=None, help="JSON merged into the harness call"
    )
    parser.add_argument("--modify-params", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--force-tool-choice", action="store_true")
    parser.add_argument("--tag", default="base")
    args = parser.parse_args()

    key = pc.load_key_into_process()
    pc.install_http_capture()
    pc.install_litellm_log_capture()
    if args.modify_params:
        litellm.modify_params = True
    call_extra = json.loads(args.call_extra) if args.call_extra else None

    natural_call: dict[str, Any] | None = None
    for scenario in args.scenarios.split(","):
        scenario = scenario.strip()
        if scenario in ("S0n", "S5") and natural_call is None:
            print(f"{args.model} {scenario} skipped: the model made no tool call in S0")
            continue
        record = await run_one(
            args.model,
            args.level,
            scenario,
            key,
            args.only_provider,
            call_extra,
            args.tag,
            args.max_tokens,
            natural_call,
            args.force_tool_choice,
        )
        if scenario == "S0" and record.get("ok"):
            raw = (record["http"][-1].get("response_json") or {}).get("choices")
            raw_message = (raw or [{}])[0].get("message") or {}
            if raw_message.get("tool_calls"):
                natural_call = pc.natural_call_from_raw(raw_message)
        pc.append_jsonl(pc.OUT_DIR / "layer1.jsonl", record, key)
        print(one_line(pc.scrub(record, key)), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
```

### `layer2.py`

```python
"""Layer 2: the same case through Kiln's own adapter (adapter_for_task + invoke).

Usage (from the Kiln repo root):
    uv run python <this file> --model anthropic/claude-haiku-5.5 --level high

Flows, each one `adapter.invoke` call with AdapterConfig(allow_saving=False):
  natural_first      invoke(QUESTION), return_on_tool_call=True. The model is
                     expected to ask for get_user_info and Kiln returns.
  natural_resume     Kiln's existing resume path with the model-made call:
                     prior_trace = trace of natural_first, input = tool result.
  harness_resume     S1. prior_trace = [system, user, harness-written call],
                     input = tool result carrying the harness call's id.
  harness_resume_stream  The same through adapter.invoke_openai_stream. The
                     capture cannot parse a streamed response body, so for this
                     flow only Kiln's own outputs are recorded.
  harness_premessage S4. prior_trace = [system, harness-written call, tool
                     result], input = the user's question.
  natural_inloop     invoke(QUESTION), return_on_tool_call=False, with a tool Kiln
                     can run itself. Shows what Kiln sends back for a model-made
                     call inside one invoke.

Every flow is appended as one JSON line to out/layer2.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import probe_common as pc


def make_runnable_adapter(slug: str, level: str | None):
    from kiln_ai.adapters.adapter_registry import adapter_for_task
    from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
    from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
    from kiln_ai.datamodel.tool_id import build_kiln_unmanaged_tool_id
    from kiln_ai.tools.base_tool import ToolCallResult, UnmanagedKilnTool

    class RunnableUserInfoTool(UnmanagedKilnTool):
        async def run(self, context=None, **kwargs) -> ToolCallResult:
            return ToolCallResult(output=pc.TOOL_RESULT)

    tool = RunnableUserInfoTool(
        tool_id=build_kiln_unmanaged_tool_id(pc.TOOL_NAME),
        name=pc.TOOL_NAME,
        description=pc.TOOL_DESCRIPTION,
        parameters_schema={"type": "object", "properties": {}},
    )
    model_name, _ = pc.kiln_model_for_slug(slug)
    fields: dict[str, Any] = {
        "model_name": model_name,
        "model_provider_name": "openrouter",
        "prompt_id": "simple_prompt_builder",
        "structured_output_mode": "default",
        "temperature": 1,
        "top_p": 1,
    }
    if level is not None:
        fields["thinking_level"] = level
    return adapter_for_task(
        pc.make_task(),
        KilnAgentRunConfigProperties(**fields),
        AdapterConfig(
            allow_saving=False, return_on_tool_call=False, unmanaged_tools=[tool]
        ),
    )


def trace_shape(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    shape = []
    for m in trace or []:
        shape.append(
            {
                "role": m.get("role"),
                "keys": sorted(m.keys()),
                "content_len": len(m.get("content") or "")
                if isinstance(m.get("content"), str)
                else None,
                "reasoning_content_len": len(m.get("reasoning_content") or ""),
                "tool_calls": [
                    tc["function"]["name"] for tc in (m.get("tool_calls") or [])
                ],
            }
        )
    return shape


async def run_flow(
    flow: str,
    slug: str,
    level: str | None,
    adapter: Any,
    key: str,
    input: Any,
    prior_trace: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], Any]:
    provider = adapter.model_provider()
    record: dict[str, Any] = {
        "ts": pc.now_ms(),
        "layer": 2,
        "model": slug,
        "flow": flow,
        "thinking_level": level,
        "provider_reasoning_capable": provider.reasoning_capable,
        "input": input,
        "prior_trace": prior_trace,
    }
    pc.CAPTURED.clear()
    pc.LITELLM_LOG.lines.clear()
    run = None
    try:
        if flow.endswith("_stream"):
            stream = adapter.invoke_openai_stream(input=input, prior_trace=prior_trace)
            chunks = 0
            async for _ in stream:
                chunks += 1
            record["stream_chunks"] = chunks
            run = stream.task_run
        else:
            run = await adapter.invoke(input=input, prior_trace=prior_trace)
        intermediate = run.intermediate_outputs or {}
        record["ok"] = True
        record["output"] = run.output.output if run.output else None
        record["is_toolcall_pending"] = run.is_toolcall_pending
        record["intermediate_output_keys"] = sorted(intermediate.keys())
        record["kiln_reasoning_len"] = len(intermediate.get("reasoning") or "")
        record["trace_shape"] = trace_shape(run.trace)
        record["trace"] = run.trace
    except Exception as e:
        record["ok"] = False
        record["error_type"] = type(e).__name__
        record["error_message"] = str(e)
        cause = e.__cause__
        if cause is not None:
            record["error_cause"] = f"{type(cause).__name__}: {cause}"

    record["litellm_log"] = list(pc.LITELLM_LOG.lines)
    record["http"] = [
        {
            "status": c.get("status"),
            "request_json": c.get("request_json"),
            "response_summary": pc.summarize_raw_response(c.get("response_json")),
            "response_json": c.get("response_json"),
        }
        for c in pc.CAPTURED
    ]
    record["checks"] = pc.answer_checks("S1", record.get("output") or "")
    pc.append_jsonl(pc.OUT_DIR / "layer2.jsonl", record, key)

    scrubbed = pc.scrub(record, key)
    if scrubbed["ok"]:
        calls = [
            (
                h["response_summary"].get("provider"),
                h["response_summary"].get("reasoning_tokens"),
                h["response_summary"].get("cost"),
            )
            for h in scrubbed["http"]
        ]
        print(
            f"{slug} {flow} OK pending={scrubbed['is_toolcall_pending']} "
            f"kiln_reasoning_len={scrubbed['kiln_reasoning_len']} "
            f"http_calls(provider,reasoning_tokens,cost)={calls} "
            f"checks={scrubbed['checks']}\n    output: {(scrubbed['output'] or '')[:160]!r}",
            flush=True,
        )
    else:
        print(
            f"{slug} {flow} ERROR {scrubbed['error_type']}: "
            f"{scrubbed['error_message'][:1500]}",
            flush=True,
        )
    return record, run


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--level", default=None)
    parser.add_argument(
        "--flows",
        default="natural_first,natural_resume,harness_resume,harness_premessage,natural_inloop",
    )
    args = parser.parse_args()
    flows = [f.strip() for f in args.flows.split(",")]

    key = pc.load_key_into_process()
    pc.install_http_capture()
    pc.install_litellm_log_capture()

    slug, level = args.model, args.level
    adapter = pc.make_adapter(slug, level, return_on_tool_call=True)

    # Kiln's own system and user messages for this task and question, taken from
    # the formatter the adapter would use on a first run.
    formatter = adapter.build_chat_formatter(pc.QUESTION, None)
    first_turn = formatter.next_turn()
    from kiln_ai.adapters.chat.chat_formatter import chat_message_to_dict

    kiln_head = [chat_message_to_dict(m) for m in first_turn.messages]
    system_message, user_message = kiln_head[0], kiln_head[1]

    run1 = None
    if "natural_first" in flows:
        _, run1 = await run_flow(
            "natural_first", slug, level, adapter, key, pc.QUESTION, None
        )

    if "natural_resume" in flows:
        if run1 is not None and run1.is_toolcall_pending:
            pending = run1.trace[-1]["tool_calls"]
            results = [
                {"tool_call_id": tc["id"], "content": pc.TOOL_RESULT} for tc in pending
            ]
            await run_flow(
                "natural_resume", slug, level, adapter, key, results, run1.trace
            )
        else:
            print(f"{slug} natural_resume skipped: no pending tool call")

    if "harness_resume" in flows:
        prior = [system_message, user_message, pc.harness_call()]
        result = {"tool_call_id": pc.HARNESS_CALL_ID, "content": pc.TOOL_RESULT}
        await run_flow("harness_resume", slug, level, adapter, key, result, prior)

    if "harness_resume_stream" in flows:
        # Same as harness_resume, through Kiln's streaming entry point.
        prior = [system_message, user_message, pc.harness_call()]
        result = {"tool_call_id": pc.HARNESS_CALL_ID, "content": pc.TOOL_RESULT}
        await run_flow(
            "harness_resume_stream", slug, level, adapter, key, result, prior
        )

    if "harness_premessage" in flows:
        prior = [system_message, pc.harness_call(), pc.tool_result()]
        await run_flow(
            "harness_premessage", slug, level, adapter, key, pc.QUESTION, prior
        )

    if "natural_inloop" in flows:
        inloop_adapter = make_runnable_adapter(slug, level)
        await run_flow(
            "natural_inloop", slug, level, inloop_adapter, key, pc.QUESTION, None
        )


if __name__ == "__main__":
    asyncio.run(main())
```

### `sweep.py`

```python
"""Width sweep: S0, S0n and S1 only, on more of the reasoning models Kiln lists
on OpenRouter. Reuses layer1.run_one, so the records land in out/layer1.jsonl
with tag "sweep".

Usage (from the Kiln repo root):
    uv run python <this file> [slug ...]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import probe_common as pc
from layer1 import one_line, run_one

DEFAULT_SLUGS = [
    "openai/gpt-5.4-mini",
    "openai/gpt-5-mini",
    "openai/gpt-oss-20b",
    "google/gemini-3-flash-preview",
    "google/gemini-3.5-flash-lite",
    "google/gemini-2.5-flash",
    "google/gemma-4-31b-it",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-r1-0528",
    "qwen/qwen3-235b-a22b-thinking-2507",
    "minimax/minimax-m3",
    "z-ai/glm-5.1",
    "x-ai/grok-4.7",
    "thinkingmachines/inkling-small",
    "tencent/hy4",
    "meta/muse-spark-open",
    "nvidia/nemotron-3-super-120b-a12b",
    "stepfun/step-3.7-flash",
    "bytedance-seed/seed-1.6-flash",
]


def level_for(slug: str) -> str | None:
    """Kiln's default thinking level for the model, unless that default is off,
    in which case 'medium' (or the first level that is not 'none')."""
    _, provider = pc.kiln_model_for_slug(slug)
    levels = list((provider.available_thinking_levels or {}).values())
    if not levels:
        return None
    default = provider.default_thinking_level
    if default and default != "none":
        return default
    if "medium" in levels:
        return "medium"
    return next(level for level in levels if level != "none")


async def main() -> None:
    key = pc.load_key_into_process()
    pc.install_http_capture()
    pc.install_litellm_log_capture()
    slugs = sys.argv[1:] or DEFAULT_SLUGS
    for slug in slugs:
        level = level_for(slug)
        natural_call = None
        for scenario in ("S0", "S0n", "S1"):
            if scenario == "S0n" and natural_call is None:
                print(f"{slug} S0n skipped: the model made no tool call in S0")
                continue
            record = await run_one(
                slug, level, scenario, key, None, None, "sweep", 2000, natural_call
            )
            if scenario == "S0" and record.get("ok"):
                choices = (record["http"][-1].get("response_json") or {}).get("choices")
                raw_message = (choices or [{}])[0].get("message") or {}
                if raw_message.get("tool_calls"):
                    natural_call = pc.natural_call_from_raw(raw_message)
            pc.append_jsonl(pc.OUT_DIR / "layer1.jsonl", record, key)
            print(one_line(pc.scrub(record, key)), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
```

### `tabulate.py`

Builds the tables in this file from the recorded JSON lines.

```python
"""Build the markdown result tables from out/layer1.jsonl and out/layer2.jsonl."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

OUT = Path(__file__).parent / "out"
ALL_SCENARIOS = ["S0", "S0n", "S0c", "S1", "S2", "S3", "S4"]
SWEEP_SCENARIOS = ["S0", "S0n", "S1"]
REASONING_KEYS = ("reasoning", "reasoning_effort", "thinking")
TIER_WORDS = ("gold", "aurora", "silver", "borealis", "bronze", "cirrus")


def answer_flags(scenario: str, content: str) -> tuple[bool, bool]:
    """(used, correct). "used" means the answer states a fact that is only in the
    tool result. "correct" goes by the last support hub the answer names, or, when
    it names none, by the last line that names a tier. Every answer this marks
    wrong was also read by hand."""
    text = (content or "").lower()
    hubs = {hub: text.rfind(hub) for hub in ("aurora", "borealis", "cirrus")}
    last_hub = max(hubs, key=lambda hub: hubs[hub]) if max(hubs.values()) >= 0 else ""
    verdict = ""
    for line in reversed(text.splitlines()):
        if any(word in line for word in TIER_WORDS):
            verdict = line
            break
    if scenario == "S3":
        correct = last_hub == "cirrus" if last_hub else "bronze" in verdict
        used = correct or "7731" in text or "odd" in text
        return used, correct
    used = any(fact in text for fact in ("dana", "lisbon", "7731"))
    if last_hub:
        correct = last_hub == "aurora"
    else:
        correct = "gold" in verdict and not any(
            word in verdict for word in ("silver", "bronze")
        )
    return used, correct


def cell(r: dict) -> str:
    if not r["ok"]:
        return f"**ERROR {r.get('error_status')}**"
    s = r["summary"]
    tokens = s.get("reasoning_tokens")
    if s.get("finish_reason") == "error":
        return f"**host error in body**, r={tokens}"
    if s.get("tool_calls"):
        return f"ok, r={tokens}, model calls tool"
    used, correct = answer_flags(r["scenario"], s.get("content", ""))
    return (
        f"ok, r={tokens}, {'used' if used else 'NOT used'}"
        f"{'' if correct else ', wrong answer'}"
    )


def sent_reasoning(r: dict) -> str:
    sent = (r["http"][-1]["request_json"] if r["http"] else {}) or {}
    return json.dumps({k: sent[k] for k in REASONING_KEYS if k in sent})


def host(r: dict) -> str:
    served_by = (r.get("summary") or {}).get("provider")
    if served_by:
        return served_by
    raw = (r["http"][-1].get("response_json") if r["http"] else None) or {}
    error_host = ((raw.get("error") or {}).get("metadata") or {}).get("provider_name")
    if error_host:
        return error_host
    return "none (OpenRouter routing error)"


def grouped(records: list[dict]) -> "OrderedDict[tuple, dict]":
    rows: "OrderedDict[tuple, dict]" = OrderedDict()
    for r in records:
        row = rows.setdefault(
            (r["model"], r["tag"]), {"hosts": [], "sent": [], "cells": {}}
        )
        if host(r) not in row["hosts"]:
            row["hosts"].append(host(r))
        if r["scenario"] != "S2" and sent_reasoning(r) not in row["sent"]:
            row["sent"].append(sent_reasoning(r))
        row["cells"].setdefault(r["scenario"], []).append(cell(r))
    return rows


def wide_table(rows: "OrderedDict[tuple, dict]", scenarios: list[str]) -> list[str]:
    lines = [
        "| Model | Run | Host that served it | Reasoning params in the request body | "
        + " | ".join(scenarios)
        + " |",
        "|" + "---|" * (4 + len(scenarios)),
    ]
    for (model, tag), row in rows.items():
        cells = [" / ".join(row["cells"].get(s, ["-"])) for s in scenarios]
        lines.append(
            f"| `{model}` | {tag} | {', '.join(row['hosts'])} | "
            f"`{' or '.join(row['sent'])}` | " + " | ".join(cells) + " |"
        )
    return lines


def long_table(rows: "OrderedDict[tuple, dict]") -> list[str]:
    lines = [
        "| Model | Run | Host that served it | Scenario | Result |",
        "|---|---|---|---|---|",
    ]
    for (model, tag), row in rows.items():
        for scenario, cells in row["cells"].items():
            lines.append(
                f"| `{model}` | {tag} | {', '.join(row['hosts'])} | {scenario} | "
                f"{' / '.join(cells)} |"
            )
    return lines


def layer1_sections() -> dict[str, str]:
    records = [
        json.loads(line)
        for line in open(OUT / "layer1.jsonl")
        if json.loads(line)["tag"] != "smoke"
    ]

    def pick(test) -> "OrderedDict[tuple, dict]":
        return grouped([r for r in records if test(r["tag"])])

    def is_pin(tag: str) -> bool:
        return tag.startswith("pin-") or tag.startswith("repeat-xhigh")

    return {
        "main": "\n".join(wide_table(pick(lambda t: t == "base"), ALL_SCENARIOS)),
        "pinned": "\n".join(wide_table(pick(is_pin), ALL_SCENARIOS)),
        "sweep": "\n".join(wide_table(pick(lambda t: t == "sweep"), SWEEP_SCENARIOS)),
        "other": "\n".join(
            long_table(pick(lambda t: t not in ("base", "sweep") and not is_pin(t)))
        ),
        "totals": (
            f"{len(records)} calls, summed `usage.cost` "
            f"${sum((r['summary'].get('cost') or 0) for r in records):.4f}"
        ),
    }


def layer2_table() -> tuple[str, str]:
    records = [json.loads(line) for line in open(OUT / "layer2.jsonl")]
    lines = [
        "| Model | Flow | Result | Kiln-side error | Reasoning tokens per LLM call | "
        'Chars in Kiln `intermediate_outputs["reasoning"]` | Answer used tool result |',
        "|---|---|---|---|---|---|---|",
    ]
    total = 0.0
    for r in records:
        tokens = [h["response_summary"].get("reasoning_tokens") for h in r["http"]]
        if r["flow"].endswith("_stream"):
            tokens = "not captured (streamed)"
        total += sum((h["response_summary"].get("cost") or 0) for h in r["http"])
        if r["ok"]:
            pending = r["is_toolcall_pending"]
            flags = answer_flags("S1", r.get("output") or "")
            used = (
                "-"
                if pending
                else ("yes" if flags[0] else "no")
                + ("" if flags[1] else ", wrong answer")
            )
            lines.append(
                f"| `{r['model']}` | {r['flow']} | "
                f"{'ok, tool call pending' if pending else 'ok'} | none | {tokens} | "
                f"{r['kiln_reasoning_len']} | {used} |"
            )
        else:
            lines.append(
                f"| `{r['model']}` | {r['flow']} | **ERROR** | "
                f"{r['error_type']}: {r['error_message'][:200]} | {tokens} | - | - |"
            )
    totals = (
        f"{len(records)} invokes, {sum(len(r['http']) for r in records)} LLM calls, "
        f"summed `usage.cost` of the non-streamed calls ${total:.4f}"
    )
    return "\n".join(lines), totals


if __name__ == "__main__":
    for name, text in layer1_sections().items():
        print(f"## {name}\n{text}\n")
    table, totals = layer2_table()
    print(table)
    print(totals)
```
