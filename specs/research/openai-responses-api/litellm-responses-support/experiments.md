# Experiments: how the findings were observed

No OpenAI or Azure key was used and no paid call was made. Every wire-level claim in this directory comes from LiteLLM 1.102.0 (Kiln's virtualenv) talking to a local fake HTTP server. That server records each request body and replies with canned OpenAI Responses or Chat Completions payloads.

All files are in `/tmp/claude-0/-home-user-Kiln/dd147251-f363-5e17-95c4-80813a10f3ed/scratchpad/litellm_wire/` (outside the repo).

| Script | What it checks | Output |
|---|---|---|
| `fake_server.py` | Threaded `http.server` that records requests and serves `SCENARIO["responses"]` (JSON or SSE) and `SCENARIO["chat"]` | n/a |
| `routing_check.py` | Calls `litellm.main.responses_api_bridge_check()` directly for 27 model/provider/tools/effort/base combinations, then 8 end-to-end `acompletion()` calls | printed in [routing-rules.md](./routing-rules.md) |
| `request_mapping.py` | Captures bridged `/v1/responses` bodies for history, tools, `tool_choice`, `response_format`, `reasoning_effort` (string, dict, `max`), `reasoning_summary`, `store`, `include`, `temperature`, `top_p`, `logprobs`, `n`, `allowed_openai_params`, `cache_control_injection_points`, `stream_options` | `request_mapping.out` |
| `misc_params_check.py` | `verbosity`, unknown `extra_body` keys, `prompt_cache_key`, `service_tier`, `safety_identifier`, `n`/`seed`, Anthropic `thinking_blocks`, reasoning items without id | `misc_params_check.out` |
| `chat_path_leak_check.py` | Whether `include`/`store` leak into `/v1/chat/completions` when a call is not bridged | `chat_path_leak_check.out` |
| `reply_mapping.py` | Non-streamed reply mapping: text+tool call, multiple tool calls, multiple reasoning items, incomplete; usage and cost | `reply_mapping.out` |
| `stream_mapping.py` (+ `stream_mapping_events.py`) | Streamed translation of a realistic SSE sequence (two summary parts, text, function call, completed); `stream_chunk_builder` result | `stream_mapping.out` |
| `native_and_azure.py` | Native `aresponses()` non-streamed and streamed (types, id encoding, cost, `previous_response_id` decoding); Azure bridge routing and URLs | `native_and_azure.out` |
| `fake_stream_check.py`, `azure_stream_check.py` | Whether streaming is native or faked for unknown OpenAI model names and Azure deployment names | `.out` files |
| `failed_stream_check.py` | Exceptions for `response.failed` (streamed) and `status: failed` (non-streamed) | `failed_stream_check.out` |

Run any of them with:

```bash
cd /tmp/claude-0/-home-user-Kiln/dd147251-f363-5e17-95c4-80813a10f3ed/scratchpad/litellm_wire
NO_PROXY=127.0.0.1,localhost /home/user/Kiln/.venv/bin/python <script>.py
```

Each script sets `LITELLM_LOCAL_MODEL_COST_MAP=True` before importing LiteLLM, so results use the bundled model map, not the copy fetched from GitHub.

Limits:

- The fake server does not validate requests the way OpenAI does. These runs show what LiteLLM sends and how it reads canned replies, not whether OpenAI accepts a given body (for example `"strict": null`, reasoning items with `id` and `encrypted_content` under `store: false`, or `include` on Chat Completions).
- The automatic "unset effort" routing arm only fires for `api.openai.com` hosts. It was exercised by calling `responses_api_bridge_check()` directly, not end to end, because the fake server is on `127.0.0.1`.

Newer LiteLLM versions were read, never imported or run. Wheels for 1.102.4, 1.103.0, 1.103.4, 1.103.5, 1.103.10, 1.104.8, 1.105.0, 1.105.7, 1.106.0, 1.106.1, 1.106.6 and 1.108.0rc1 were downloaded from PyPI into separate empty directories under the scratchpad (`dl_litellm_<version>/`), checked against PyPI's sha256, unzipped selectively, and diffed or grepped. The full 1.102.0 to 1.106.6 diff of the bridge transformation is saved as `litellm_wire/diff_transformation_102_to_106.diff`.
