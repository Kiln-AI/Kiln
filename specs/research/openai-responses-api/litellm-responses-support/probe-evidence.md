# Probe evidence: wire captures of litellm 1.102.0

**Method.** The scripts in [`probes/`](./probes/) start a local HTTP server that records each request's path and JSON body and returns a canned Chat Completions or Responses payload. They then call `litellm.completion()` / `acompletion()` / `aresponses()` with `api_base` pointed at that server, `drop_params=True` (as Kiln does), and `LITELLM_LOCAL_MODEL_COST_MAP=True` (bundled map). No real provider was called. The results show what LiteLLM *sends* and how it *parses* a given response. They say nothing about how OpenAI would respond.

Run with (the scripts are stored as `.py.txt` so the repo's ruff/ty checks skip them): copy `probes/*.py.txt` to a scratch directory, rename them to `.py`, and run `cd /home/user/Kiln && PYTHONPATH=<scratch> uv run python <scratch>/probe.py`. probe2–4 import `probe.py`.

Caveat: because `api_base` is custom, the gpt-5.4+ auto-route only fires when `reasoning_effort` is explicit (see the bridge doc). I checked the default-base behaviour separately by calling `responses_api_bridge_check()` directly. That matrix is in [completion-to-responses-bridge.md](./completion-to-responses-bridge.md).

## Results (`probe.py`, `probe2.py`, `probe4.py`)

| # | Call | Path hit | Key body fields | Parsed result |
|---|---|---|---|---|
| A | `openai/gpt-5.5`, effort `high` | `/v1/chat/completions` | `reasoning_effort: "high"` | – |
| B | `openai/gpt-5.5`, effort `high`, function tool | **`/v1/responses`** | `instructions: "sys"`, `reasoning: {effort: "high"}`, tool `{type: function, name, parameters, strict: null, description}` | **2 choices**: `finish ['stop','tool_calls']`; `choices[0].tool_calls` empty; reasoning_items on choice 0; usage reasoning_tokens=12, cached_tokens=4; cost 0.000632 |
| C | `openai/gpt-5.5`, effort `none`, tool | chat | `reasoning_effort: "none"`, tools | – |
| D | `openai/gpt-5.2`, effort `high`, tool | chat | `reasoning_effort: "high"`, tools | – |
| E | `openai/responses/gpt-5.5`, effort `low`, `response_format` json_schema strict | `/v1/responses` | `text: {format: {type: json_schema, name: "out", schema, strict: true}}` | content `{"a": 1}`, `reasoning_content: "thinking..."` (from summary) |
| F | `openai/gpt-5.5-pro`, effort `high` | `/v1/responses` (cost map `mode: responses`) | `reasoning: {effort: "high"}` | – |
| G | `openai/responses/gpt-5.5`, effort dict `{effort: high, summary: auto}`, `include=[reasoning.encrypted_content]`, `store=False` | `/v1/responses` | all three passed through verbatim | reasoning_items carry `encrypted_content` |
| H | `openai/responses/gpt-5.5`, effort `none`, `logprobs=True`, `top_logprobs=3` | `/v1/responses` | `top_logprobs: 3`, **no `logprobs`, no `include` for logprobs** | – |
| I | `openai/gpt-5.5`, `xhigh` | chat | `reasoning_effort: "xhigh"` | – |
| J | `openai/gpt-5`, `xhigh` | chat | **no reasoning_effort (dropped)** | – |
| K | `openrouter/openai/gpt-5.5`, `high`, tool | OpenRouter chat | `reasoning_effort: "high"` top-level, `usage: {include: true}` | – |
| L | `openrouter/responses/openai/gpt-5.5`, `high`, tool | **`/v1/responses`** (OpenRouter native) | `model: "openai/gpt-5.5"`, `reasoning: {effort: high}` | same 2-choice split as B |
| M | `azure/responses/my-deploy`, `high` | `/v1/openai/responses?api-version=2025-04-01-preview` | `model: "my-deploy"`, `reasoning` | (the mock returned the wrong shape, so a parse error; this only shows the route) |
| N | `openai/o3`, `high`, tool | chat | `reasoning_effort`, tools | – |
| O | `openai/gpt-5.5`, tool, no effort, custom base | chat | tools only | – |
| P | `openai/responses/gpt-5.5`, multi-turn with assistant `tool_calls` + `reasoning_items` + tool result | `/v1/responses` | input: user msg → `{type: reasoning, id: rs_1, encrypted_content}` → `{type: function_call, call_id, name, arguments}` → `{type: function_call_output, call_id, output: [{type: input_text, text: "3"}]}` | – |
| Q | `openai/responses/gpt-5.5`, `verbosity="low"` | `/v1/responses` | **no verbosity / no `text.verbosity`** | – |
| R | `openai/responses/gpt-5.5`, `temperature=0.2`, effort `high` | `/v1/responses` | **temperature dropped** | – |
| S | `max_tokens=500`, `parallel_tool_calls=False`, `tool_choice="required"` | `/v1/responses` | `max_output_tokens: 500`, `parallel_tool_calls: false`, `tool_choice: "required"` | – |
| T | `tool_choice={"type":"function","function":{"name":"add"}}` | `/v1/responses` | `tool_choice: {type: function, name: add}` | – |
| U | `route_all_chat_openai_to_responses=True`, `openai/gpt-4.1` | `/v1/responses` | `instructions` | – |
| V | `openai/gpt-5.5`, `minimal` | chat | **dropped** | – |
| W | `openai/responses/gpt-5.5`, `minimal` | responses | **dropped** | – |
| X | `openai/responses/gpt-5`, `xhigh` | responses | **dropped** | – |
| Y | `openai/gpt-5`, `none` | chat | `reasoning_effort: "none"` (not validated) | – |
| Z | `openai/gpt-5.5-pro`, `low` | responses | **dropped** | – |

## Streaming (`probe_stream.py`)

`acompletion(model="openai/responses/gpt-5.5", stream=True, tools=..., reasoning_effort="low", stream_options={"include_usage": True})` against an SSE mock that emits reasoning, text and function_call items:

```
PATH /v1/responses stream True stream_options None
CHUNK content= None reasoning= 'plan' tool_calls= [] finish= None
CHUNK content= 'Hi ' ...
CHUNK content= 'there' ...
CHUNK tool_calls= [(0, 'fc_1', 'add', '')]
CHUNK tool_calls= [(0, None, None, '{"a":1}')]
CHUNK content= '' reasoning_items= True
CHUNK finish= tool_calls
CHUNK usage= 20
REBUILT content 'Hi there' tool_calls ['add'] reasoning 'plan' usage 30
```

Observations:
- `stream_options` was **not** forwarded to the Responses request. Usage still arrived because Responses always reports usage in `response.completed`.
- The streamed result rebuilds into **one** choice. The two-choice split only happens on the non-streaming path.
- The tool-call id was `fc_1` (item id) and not `call_1`. That is because the mock's `call_1` matches the Bedrock-Mantle heuristic `call_\d+`. It is a mock artifact, not an OpenAI behaviour.

## Direct `aresponses()` (`probe3.py`)

- The return type is `ResponsesAPIResponse` (a Pydantic `BaseLiteLLMOpenAIResponseObject`).
- The body was sent exactly as given: `include`, `instructions`, `reasoning {effort, summary}`, `store: false`, `text.format` json_schema.
- `output_text` works. `usage` is a `ResponseAPIUsage` with `cached_tokens` and `reasoning_tokens`.
- `_hidden_params["response_cost"]` equals `litellm.completion_cost(completion_response=r)`.
- `r.id` is LiteLLM-encoded: `resp_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOm9wZW5haTttb2RlbF9pZDpOb25lO3Jlc3BvbnNlX2lkOnJlc3BfMTIz`.
