# Probe results: Kiln's adapter through LiteLLM 1.102's completion→Responses bridge

**Method.** I ran the real, unmodified `LiteLlmAdapter` (repo commit `c215b3e4`, litellm 1.102.0 from `.venv`) against a local fake OpenAI server. The server answers `/v1/responses` with canned Responses API JSON or SSE, and answers `/v1/chat/completions` with a canned chat reply. That shows which endpoint LiteLLM hits for each Kiln request shape, the exact body it sends, and what Kiln builds from the reply. Model: `gpt_6_1_sol` on provider `openai`, with `base_url` pointed at the fake server and a dummy `OPENAI_API_KEY`. **No real API calls were made.** So this checks Kiln↔LiteLLM translation only, not what OpenAI accepts. The fake replies are my approximation of Responses output, and real OpenAI behaviour (for example whether `strict: null` or `summary` with effort `none` is accepted) is not tested. The script is in the appendix. It lived in a scratch directory and is not committed.

## 1. When does LiteLLM route a `completion()` call to `/v1/responses`?

Source: `responses_api_bridge_check`, `.venv/.../litellm/main.py:1047-1135`. It is called twice inside `completion()`: early (`main.py:5349`) and again with the tools and `reasoning_effort` (`main.py:5596-5610`). A request is bridged when any of these hold:

1. **LiteLLM's model map says `mode: "responses"`** for the model (for example `gpt-5.4-pro`, `gpt-5.2-pro`, `gpt-5-pro`, `gpt-5-codex`).
2. **The model name starts with `responses/`** and isn't in the map, e.g. `openai/responses/gpt-6.1-sol` or `azure/responses/<deployment>` (`main.py:1070-1083`). The prefix is stripped before the call.
3. **Global `litellm.route_all_chat_openai_to_responses`**, or env `LITELLM_ROUTE_ALL_CHAT_OPENAI_TO_RESPONSES=true` (`litellm/__init__.py:263-265`). This applies to every `openai`-provider call.
4. **OpenAI/Azure GPT-5-family name, together with** either (a) `reasoning_effort` plus a reasoning-summary alias (`reasoning_summary` / `reasoningSummary`, top level or in `extra_body`), or (b) a gpt-5.4+ name (including `gpt-6*`) **with a function tool and reasoning active** (`reasoning_effort != "none"`; an unset effort also counts on api.openai.com and Azure) (`main.py:1086-1133`).

Probe of `responses_api_bridge_check` for model names Kiln uses (provider `openai`, with or without one function tool):

| model | effort unset | effort `medium` | effort `none` |
|---|---|---|---|
| `gpt-5.2` | chat / chat | chat / chat | chat / chat |
| `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.5`, `gpt-6-astra`, `gpt-6.1-sol` | chat / **responses** | chat / **responses** | chat / chat |
| `gpt-5.4-pro`, `gpt-5.2-pro`, `gpt-5-pro`, `gpt-5-codex` | **responses** always | | |
| `gpt-6-sol-pro` (not in litellm's map) | mode unknown / **responses** with tools | | |
| `o3` | chat always | | |

(cells are "no tools / with tools")

**Version history.** This automatic routing for gpt-5.4+ (case 4b) first shows up in **litellm 1.82.2** (released 2026-03-13 per PyPI). I downloaded the 1.81.16, 1.82.0, 1.82.1 and 1.82.2 wheels and grepped `main.py` for `is_model_gpt_5_4_plus_model`: zero hits through 1.82.1, one hit from 1.82.2 on. In 1.82.x the condition was `tools and reasoning_effort is not None`, which also counted `"none"`. 1.102.0 refines it. Kiln's `uv.lock` was at **litellm 1.81.16** when `supports_function_calling=False` with the comment "until Kiln routes these models to /v1/responses" was first added for `gpt-5.4` (merge `985d9616`, 2026-05-04). That flag was then copied to every later gpt-5.4+ OpenAI entry (`ml_model_list.py:824, 884, 974, 1065, 1122, 1181, 1240, 1296, 1397`). Kiln moved to 1.102 on 2026-09-30 (`df707a20`). **So the reason those models had function calling turned off (no automatic routing) no longer holds at the pinned version.** That is an inference from source. A paid test against real OpenAI would confirm it.

## 2. Scenario results

| # | Scenario | Endpoint hit | Request body (key fields) | Kiln result |
|---|---|---|---|---|
| 1 | Unstructured task, `add` tool, effort `high`, non-streaming. Fake reply 1 = `[reasoning, function_call]`, reply 2 = `[reasoning, message]` | `/v1/responses` ×2 (**automatic, no Kiln change**) | `instructions`, `reasoning: {effort: "high"}`, `temperature: 1.0`, `tool_choice: "auto"`, flat `tools` with `strict: null`. The second call's `input` = user msg, `reasoning` item (id + summary), `function_call`, `function_call_output` | ✅ Tool ran. Output `"The answer is 4"`. `intermediate_outputs.reasoning` filled from the summary. Usage `100/50/150`, `cached_tokens=40`, `cost=0.000624` on each trace message. The trace is normal chat shape. |
| 2 | Same, but reply 1 = `[reasoning, message("Let me add those."), function_call]` (a preamble), non-streaming | `/v1/responses` ×1 | same | ❌ **Wrong result.** Output = `"Let me add those."` and the tool never ran. The bridge returned 2 choices and Kiln reads `choices[0]` (`litellm_adapter.py:457`). |
| 3 | Same as 2, **streaming** (`invoke_ai_sdk_stream`) | `/v1/responses` ×2, `stream: true` | same | ✅ Tool ran, final `"The answer is 4"`. AI SDK events: reasoning start/delta/end, text, tool-input-*, tool-output-available, finish. **But** the second call's `input` had **no reasoning item**, because `stream_chunk_builder` drops `reasoning_items`. |
| 4 | Structured task, json_schema, no tools, effort `max` | **`/v1/chat/completions`** | `reasoning_effort: "max"`, `response_format: json_schema` | Chat path. Per Kiln's own comment (`ml_model_list.py:549-553`), real OpenAI rejects `max` here for gpt-6.1-sol. Automatic bridging does **not** cover "effort not accepted on chat". |
| 5 | Same as 4 with model id forced to `openai/responses/gpt-6.1-sol`, effort `xhigh` | `/v1/responses` | `reasoning: {effort: "xhigh"}`, `text.format: {type: json_schema, name: "task_response", schema, strict: false}` | ✅ Output `{"answer": 4}`, reasoning captured, cost captured. |
| 6 | Structured task, `function_calling` mode (forced `task_response` tool), effort `high` | `/v1/responses` (automatic, because `task_response` is a function tool) | `tool_choice: {type: "function", name: "task_response"}`, tool `strict: true` | ✅ Output `{"answer": 4}`. |
| 7 | Same as 5 plus `top_logprobs=3` | `/v1/responses` | no `logprobs`, `top_logprobs` or `include` sent | ❌ Kiln raised "Logprobs were required, but no logprobs were returned." (expected: the bridge doesn't map logprobs) |
| 8 | No tools, effort `max`, `additional_body_options={"reasoning_summary": "auto"}` | `/v1/responses` (automatic via case 4a) | `reasoning: {effort: "max", summary: "auto"}` + `text.format` | ✅ Works non-streaming and streaming. **A one-key way to force Responses for any GPT-5-family model on openai/azure, and to get a reasoning summary back.** |
| 9 | Effort `none` + `reasoning_summary: "auto"` | `/v1/responses` | `reasoning: {effort: "none", summary: "auto"}` | Kiln side OK. Whether OpenAI accepts `summary` with effort `none` is not verified (question for subtopic 1/2). |
| 10 | Scenario 1 + `automatic_prompt_caching=True` | `/v1/responses` | no `cache_control` in the body | ✅ No leakage. |
| 11 | Scenario 1 + `additional_body_options={"store": false, "include": ["reasoning.encrypted_content"]}` | `/v1/responses` | `store: false`, `include` passed through | ✅ Non-streaming: the second call sends back `{"id": "rs_1", "summary": [...], "encrypted_content": "ENC_BLOB"}`. Streaming: the reasoning item is dropped (as in 3). The saved trace never holds `encrypted_content` (`litellm_adapter.py:965-1017`). |

### Observations that matter for design

- **Default `store`.** The bridge sends no `store` field (scenarios 1–8). Per OpenAI's API, Responses defaults to storing the response; Chat Completions does not. That is a data-retention change for Kiln users. **This is an API-semantics claim for subtopic 1 to confirm.** If Kiln sets `store: false`, it must also send `include: ["reasoning.encrypted_content"]`. Otherwise the bridge sends back reasoning items by bare id (scenario 1), and those ids only resolve when the response was stored. That second part is inference.
- **Reasoning text.** Real OpenAI returns summary text only when `reasoning.summary` is requested. By default the bridge does not request it (`transformation.py:1157-1174`), unless `litellm.reasoning_auto_summary` / `LITELLM_REASONING_AUTO_SUMMARY` is set. Those are process-global, so avoid them. Kiln should send `reasoning_summary: "auto"`, or a dict `reasoning_effort`.
- **Tool `strict: null`.** Kiln's tool definitions carry no `strict`, and the bridge copies `None` (`transformation.py:1106`). Subtopic 1 should check how Responses treats a null `strict`.

## Appendix: probe script

Run with `OPENAI_API_KEY=sk-test [STRUCTURED=1] [TOOLS=0] [EFFORT=max] [PREFIX=1] [STREAM=1] [LOGPROBS=3] [CACHE=1] [EXTRA='{"reasoning_summary":"auto"}'] uv run python bridge_probe.py <tool_then_text|preamble|json|task_response>` from the repo root.

<details><summary>bridge_probe.py</summary>

```python
"""Probe: run the real LiteLlmAdapter against a local fake OpenAI server to see
whether litellm 1.102's completion->responses bridge fires for Kiln's request
shape, and how the response comes back. No real API calls."""

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import AddTool

REQUESTS: list[tuple[str, dict]] = []
SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "tool_then_text"


def responses_body(output, usage=None):
    return {
        "id": "resp_123",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "gpt-6.1-sol",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": usage
        or {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens": 50,
            "output_tokens_details": {"reasoning_tokens": 30},
            "total_tokens": 150,
        },
    }


REASONING = {
    "type": "reasoning",
    "id": "rs_1",
    "summary": [{"type": "summary_text", "text": "I should add the numbers."}],
    "encrypted_content": "ENC_BLOB",
}


def msg(text):
    return {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


FCALL = {
    "type": "function_call",
    "id": "fc_1",
    "call_id": "call_1",
    "name": "add",
    "arguments": json.dumps({"a": 2, "b": 2}),
    "status": "completed",
}


class H(BaseHTTPRequestHandler):
    def _sse(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for i, e in enumerate(_sse_events(data)):
            e["sequence_number"] = i
            self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode())
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(n))
        REQUESTS.append((self.path, body))
        if self.path.endswith("/responses"):
            n_resp = sum(1 for p, _ in REQUESTS if p.endswith("/responses"))
            if n_resp == 1:
                if SCENARIO == "tool_then_text":
                    out = [REASONING, FCALL]
                elif SCENARIO == "json":
                    out = [REASONING, msg('{"answer": 4}')]
                elif SCENARIO == "task_response":
                    out = [REASONING, dict(FCALL, name="task_response", arguments='{"answer": 4}')]
                else:  # preamble: text + tool call in the same response
                    out = [REASONING, msg("Let me add those."), FCALL]
            else:
                out = [REASONING, msg("The answer is 4")]
            data = responses_body(out)
        else:
            data = {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1,
                "model": "x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "chat path"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        if body.get("stream") and self.path.endswith("/responses"):
            return self._sse(data)
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _sse_events(data):
    ev = [{"type": "response.created", "response": dict(data, status="in_progress", output=[], usage=None)}]
    for i, item in enumerate(data["output"]):
        if item["type"] == "reasoning":
            ev.append({"type": "response.output_item.added", "output_index": i, "item": dict(item, summary=[])})
            for si, part in enumerate(item["summary"]):
                for w in part["text"].split(" "):
                    ev.append({"type": "response.reasoning_summary_text.delta", "item_id": item["id"], "output_index": i, "summary_index": si, "delta": w + " "})
            ev.append({"type": "response.output_item.done", "output_index": i, "item": item})
        elif item["type"] == "message":
            ev.append({"type": "response.output_item.added", "output_index": i, "item": dict(item, content=[])})
            text = item["content"][0]["text"]
            for ch in [text[:5], text[5:]]:
                ev.append({"type": "response.output_text.delta", "item_id": item["id"], "output_index": i, "content_index": 0, "delta": ch})
            ev.append({"type": "response.output_item.done", "output_index": i, "item": item})
        elif item["type"] == "function_call":
            ev.append({"type": "response.output_item.added", "output_index": i, "item": dict(item, arguments="")})
            ev.append({"type": "response.function_call_arguments.delta", "item_id": item["id"], "output_index": i, "delta": item["arguments"]})
            ev.append({"type": "response.function_call_arguments.done", "item_id": item["id"], "output_index": i, "arguments": item["arguments"]})
            ev.append({"type": "response.output_item.done", "output_index": i, "item": item})
    ev.append({"type": "response.completed", "response": data})
    return ev


async def main():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    import os
    structured = os.environ.get("STRUCTURED") == "1"
    task = Task(
        name="t",
        instruction="Add numbers",
        output_json_schema=json.dumps(
            {"type": "object", "properties": {"answer": {"type": "integer"}}, "required": ["answer"]}
        )
        if structured
        else None,
    )
    cfg = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt_6_1_sol",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=os.environ.get("SOM", "json_schema"),
            thinking_level=os.environ.get("EFFORT", "high"),
        ),
        base_url=f"http://127.0.0.1:{port}/v1",
        additional_body_options={"api_key": "sk-test", **json.loads(os.environ.get("EXTRA", "{}"))},
    )
    adapter = LiteLlmAdapter(
        config=cfg,
        kiln_task=task,
        base_adapter_config=AdapterConfig(
            allow_saving=False,
            automatic_prompt_caching=os.environ.get("CACHE") == "1",
            unmanaged_tools=[AddTool()] if os.environ.get("TOOLS", "1") == "1" else None,
            top_logprobs=int(os.environ["LOGPROBS"]) if os.environ.get("LOGPROBS") else None,
        ),
    )
    if os.environ.get("PREFIX"):
        adapter._litellm_model_id = "openai/responses/gpt-6.1-sol"
    if os.environ.get("STREAM"):
        try:
            stream = adapter.invoke_ai_sdk_stream("what is 2+2")
            kinds = []
            async for ev in stream:
                kinds.append(getattr(ev, "type", type(ev).__name__))
            print("EVENTS:", kinds)
            tr = stream.task_run
            print("OUTPUT:", "output=" + repr(tr.output.output))
            print("INTERMEDIATE:", tr.intermediate_outputs)
            print("USAGE:", tr.usage)
        except Exception as e:
            print("ERROR:", type(e).__name__, str(e)[:500])
        for path, body in REQUESTS:
            b = {k: v for k, v in body.items() if k not in ("input",)}
            print("REQ", path, json.dumps(b)[:500])
            if "input" in body:
                print("   INPUT", json.dumps(body["input"])[:600])
        return
    try:
        run_output, usage = await adapter._run_returning_run_output("what is 2+2")
        print("OUTPUT:", run_output.output)
        print("INTERMEDIATE:", run_output.intermediate_outputs)
        print("USAGE:", usage)
        for m in run_output.trace or []:
            print("TRACE:", json.dumps(m, default=str)[:300])
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e)[:500])
    for path, body in REQUESTS:
        b = {k: v for k, v in body.items() if k not in ("input",)}
        print("REQ", path, json.dumps(b)[:700])
        if "input" in body:
            print("   INPUT", json.dumps(body["input"])[:900])


asyncio.run(main())
```

</details>
