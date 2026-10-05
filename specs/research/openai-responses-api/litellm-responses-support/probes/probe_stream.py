"""Streaming through the completion->responses bridge in litellm 1.102.0, against a local SSE mock."""
import json, os, threading, asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
import litellm

FINAL = {"id": "resp_1", "object": "response", "created_at": 1, "status": "completed", "model": "gpt-5.5",
  "output": [
    {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "plan"}], "encrypted_content": "ENC"},
    {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "Hi there", "annotations": []}]},
    {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "add", "arguments": "{\"a\":1}", "status": "completed"}],
  "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30, "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 12}},
  "parallel_tool_calls": True, "tool_choice": "auto", "tools": []}
EVENTS = [
  {"type": "response.created", "sequence_number": 0, "response": dict(FINAL, status="in_progress", output=[], usage=None)},
  {"type": "response.output_item.added", "sequence_number": 1, "output_index": 0, "item": {"type": "reasoning", "id": "rs_1", "summary": []}},
  {"type": "response.reasoning_summary_text.delta", "sequence_number": 2, "item_id": "rs_1", "output_index": 0, "summary_index": 0, "delta": "plan"},
  {"type": "response.output_item.done", "sequence_number": 3, "output_index": 0, "item": FINAL["output"][0]},
  {"type": "response.output_item.added", "sequence_number": 4, "output_index": 1, "item": {"type": "message", "id": "msg_1", "role": "assistant", "status": "in_progress", "content": []}},
  {"type": "response.output_text.delta", "sequence_number": 5, "item_id": "msg_1", "output_index": 1, "content_index": 0, "delta": "Hi ", "logprobs": []},
  {"type": "response.output_text.delta", "sequence_number": 6, "item_id": "msg_1", "output_index": 1, "content_index": 0, "delta": "there", "logprobs": []},
  {"type": "response.output_item.done", "sequence_number": 7, "output_index": 1, "item": FINAL["output"][1]},
  {"type": "response.output_item.added", "sequence_number": 8, "output_index": 2, "item": {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "add", "arguments": "", "status": "in_progress"}},
  {"type": "response.function_call_arguments.delta", "sequence_number": 9, "item_id": "fc_1", "output_index": 2, "delta": "{\"a\":1}"},
  {"type": "response.function_call_arguments.done", "sequence_number": 10, "item_id": "fc_1", "output_index": 2, "arguments": "{\"a\":1}"},
  {"type": "response.output_item.done", "sequence_number": 11, "output_index": 2, "item": FINAL["output"][2]},
  {"type": "response.completed", "sequence_number": 12, "response": FINAL},
]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        print("PATH", self.path, "stream", body.get("stream"), "stream_options", body.get("stream_options"))
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for ev in EVENTS:
            self.wfile.write(f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode())
        self.wfile.flush()
srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}/v1"
TOOLS = [{"type": "function", "function": {"name": "add", "parameters": {"type": "object", "properties": {"a": {"type": "number"}}}}}]

async def main():
    stream = await litellm.acompletion(model="openai/responses/gpt-5.5", api_base=BASE, api_key="sk-x",
        messages=[{"role": "user", "content": "hi"}], reasoning_effort="low", tools=TOOLS, stream=True,
        stream_options={"include_usage": True})
    chunks = []
    async for c in stream:
        chunks.append(c)
        d = c.choices[0].delta if c.choices else None
        print("CHUNK", "content=", repr(getattr(d, "content", None)), "reasoning=", repr(getattr(d, "reasoning_content", None)),
              "tool_calls=", [(t.index, t.id, t.function.name, t.function.arguments) for t in (getattr(d, "tool_calls", None) or [])],
              "finish=", c.choices[0].finish_reason if c.choices else None, "reasoning_items=", bool(getattr(d, "reasoning_items", None)) if d else None,
              "usage=", getattr(c, "usage", None) and c.usage.model_dump().get("completion_tokens"))
    rebuilt = litellm.stream_chunk_builder(chunks)
    m = rebuilt.choices[0].message
    print("REBUILT content", repr(m.content), "tool_calls", m.tool_calls and [t.function.name for t in m.tool_calls], "reasoning", repr(getattr(m, "reasoning_content", None)), "usage", rebuilt.usage and rebuilt.usage.total_tokens)
asyncio.run(main())
