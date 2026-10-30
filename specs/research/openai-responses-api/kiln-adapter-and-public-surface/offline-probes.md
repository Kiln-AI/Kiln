# Offline probes (reproduction)

All probes ran on 2026-10-30 against this checkout (commit `579014ab`, LiteLLM 1.102.0) with no network access to any provider: `respx` intercepted every HTTP call and an unmatched call would have raised. `OPENAI_API_KEY` was set to a fake value inside each script. No paid call was made. Run with `uv run python <script>` from the repo root.

## 1. Endpoint per model, request keys, usage mapping

Result:

```
gpt_5_4_pro: endpoint=responses output='pong' usage=5/1 cost=0.00033
   request keys: ['input', 'instructions', 'model', 'reasoning', 'temperature']
   reasoning: {'effort': 'medium'} reasoning_effort: None store: None
gpt_5_4: endpoint=chat output='pong' usage=5/1 cost=2.75e-05
   request keys: ['messages', 'model', 'reasoning_effort', 'temperature']
```

```python
"""Offline probe: which OpenAI endpoint does today's adapter hit for a Responses-only model
(gpt-5.4-pro, mode=responses in LiteLLM's map) vs gpt-5.4 (no tools)? respx blocks all real
network calls; any unmatched request raises."""
import asyncio
import json
import os

os.environ["OPENAI_API_KEY"] = "sk-fake-offline"
os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import httpx
import litellm
import respx

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

litellm.disable_aiohttp_transport = True

RESP_BODY = {
    "id": "resp_1", "object": "response", "created_at": 1759000000, "status": "completed",
    "model": "gpt-5.4-pro", "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
    "output": [{"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": "pong", "annotations": []}]}],
    "usage": {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6,
              "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
}
CHAT_BODY = {
    "id": "chatcmpl-1", "object": "chat.completion", "created": 1759000000, "model": "gpt-5.4",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
}


async def run(model_name: str):
    task = datamodel.Task(name="t", instruction="Reply with pong")
    with respx.mock(assert_all_called=False) as mock:
        r_route = mock.post("https://api.openai.com/v1/responses").mock(return_value=httpx.Response(200, json=RESP_BODY))
        c_route = mock.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(200, json=CHAT_BODY))
        adapter = adapter_for_task(task, KilnAgentRunConfigProperties(
            model_name=model_name, model_provider_name="openai", prompt_id="simple_prompt_builder",
            structured_output_mode="default", thinking_level="medium"),
            base_adapter_config=AdapterConfig(allow_saving=False))
        run = await adapter.invoke("ping")
        hit = "responses" if r_route.called else ("chat" if c_route.called else "none")
        req = (r_route if r_route.called else c_route).calls.last.request
        body = json.loads(req.content)
        print(f"{model_name}: endpoint={hit} output={run.output.output!r} usage={run.usage.input_tokens}/{run.usage.output_tokens} cost={run.usage.cost}")
        print("   request keys:", sorted(body.keys()))
        print("   reasoning:", body.get("reasoning"), "reasoning_effort:", body.get("reasoning_effort"), "store:", body.get("store"))
        print("   trace assistant:", run.trace[-1])

asyncio.run(run("gpt_5_4_pro"))
asyncio.run(run("gpt_5_4"))
```

## 2. Tool round trip, and a reply with text plus a tool call

Run with no argument for a reply holding only a reasoning item and a function call; with `with_text` the first reply also holds a text message before the function call.

Result:

```
=== tool call only
calls: 2 output: 'The answer is [4]'
intermediate_outputs: {}
  TRACE {'role': 'assistant', 'content': None, 'reasoning_content': 'Need to add.', 'tool_calls': [{'id': 'call_abc', ...}]}
  REQ2 input item: {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "what is 2+2"}]}
  REQ2 input item: {"id": "rs_1", "summary": [{"text": "Need to add.", "type": "summary_text"}], "type": "reasoning", "encrypted_content": "ENC123"}
  REQ2 input item: {"type": "function_call", "call_id": "call_abc", "name": "add", "arguments": "{\"a\": 2, \"b\": 2}"}
  REQ2 input item: {"type": "function_call_output", "call_id": "call_abc", "output": [{"type": "input_text", "text": "4"}]}
=== text plus tool call
calls: 1 output: 'Let me add those.'
intermediate_outputs: {'reasoning': 'Need to add.'}
  TRACE {'role': 'assistant', 'content': 'Let me add those.', 'reasoning_content': 'Need to add.'}
```

```python
"""Offline probe of Kiln's tool loop through LiteLLM's chat->responses bridge (gpt-5.4-pro, which
LiteLLM 1.102.0 routes to /v1/responses on its own). respx blocks all real network calls."""
import asyncio
import json
import os
import sys
from unittest.mock import patch

os.environ["OPENAI_API_KEY"] = "sk-fake-offline"
os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import httpx
import litellm
import respx

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import AddTool

litellm.disable_aiohttp_transport = True
WITH_TEXT = len(sys.argv) > 1 and sys.argv[1] == "with_text"

def base(output):
    return {"id": "resp_x", "object": "response", "created_at": 1759000000, "status": "completed",
            "model": "gpt-5.4-pro", "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "output": output,
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 3}}}

first_output = [
    {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "Need to add."}], "encrypted_content": "ENC123"},
]
if WITH_TEXT:
    first_output.append({"type": "message", "id": "msg_0", "status": "completed", "role": "assistant",
                         "content": [{"type": "output_text", "text": "Let me add those.", "annotations": []}]})
first_output.append({"type": "function_call", "id": "fc_1", "call_id": "call_abc", "name": "add",
                     "arguments": "{\"a\": 2, \"b\": 2}", "status": "completed"})
FIRST = base(first_output)
SECOND = base([{"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": "The answer is [4]", "annotations": []}]}])


async def main():
    task = datamodel.Task(name="t", instruction="Use tools for math")
    with respx.mock() as mock:
        route = mock.post("https://api.openai.com/v1/responses").mock(
            side_effect=[httpx.Response(200, json=FIRST), httpx.Response(200, json=SECOND)])
        adapter = adapter_for_task(task, KilnAgentRunConfigProperties(
            model_name="gpt_5_4_pro", model_provider_name="openai", prompt_id="simple_prompt_builder",
            structured_output_mode="default", thinking_level="medium"),
            base_adapter_config=AdapterConfig(allow_saving=False))
        with patch.object(adapter, "available_tools", return_value=[AddTool()]):
            try:
                run = await adapter.invoke("what is 2+2")
            except Exception as e:
                print("ERROR:", type(e).__name__, str(e)[:300])
                print("calls:", route.call_count)
                return
        print("calls:", route.call_count, "output:", repr(run.output.output))
        print("intermediate_outputs:", run.intermediate_outputs)
        for m in run.trace:
            print("  TRACE", {k: v for k, v in m.items() if k not in ("usage", "latency_ms")})
        if route.call_count > 1:
            body2 = json.loads(route.calls[1].request.content)
            print("REQ1 tools:", json.dumps(json.loads(route.calls[0].request.content).get("tools")))
            print("REQ2 keys:", sorted(body2))
            for item in body2["input"]:
                print("  REQ2 input item:", json.dumps(item)[:220])

asyncio.run(main())
```

## 3. Continuation from a saved trace

Result: the continuation request input was `user`, `function_call`, `function_call_output`, assistant `message`, new `user`. No reasoning item.

```python
"""Offline probe: what Kiln replays to /v1/responses when continuing from a saved trace (prior_trace)."""
import asyncio
import json
import os
from unittest.mock import patch

os.environ["OPENAI_API_KEY"] = "sk-fake-offline"
os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import httpx
import litellm
import respx

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import AddTool

litellm.disable_aiohttp_transport = True

def base(output):
    return {"id": "resp_x", "object": "response", "created_at": 1759000000, "status": "completed",
            "model": "gpt-5.4-pro", "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "output": output, "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}

FIRST = base([
    {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "Need to add."}], "encrypted_content": "ENC123"},
    {"type": "function_call", "id": "fc_1", "call_id": "call_abc", "name": "add", "arguments": "{\"a\": 2, \"b\": 2}", "status": "completed"}])
SECOND = base([{"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": "The answer is [4]", "annotations": []}]}])
THIRD = base([{"type": "message", "id": "msg_2", "status": "completed", "role": "assistant",
               "content": [{"type": "output_text", "text": "Yes.", "annotations": []}]}])

async def main():
    task = datamodel.Task(name="t", instruction="Use tools for math")
    rc = KilnAgentRunConfigProperties(model_name="gpt_5_4_pro", model_provider_name="openai",
        prompt_id="simple_prompt_builder", structured_output_mode="default", thinking_level="medium")
    with respx.mock() as mock:
        route = mock.post("https://api.openai.com/v1/responses").mock(
            side_effect=[httpx.Response(200, json=FIRST), httpx.Response(200, json=SECOND), httpx.Response(200, json=THIRD)])
        adapter = adapter_for_task(task, rc, base_adapter_config=AdapterConfig(allow_saving=False))
        with patch.object(adapter, "available_tools", return_value=[AddTool()]):
            run1 = await adapter.invoke("what is 2+2")
        # Simulate the saved-and-reloaded trace: TaskRun validation already ran on run1.trace.
        adapter2 = adapter_for_task(task, rc, base_adapter_config=AdapterConfig(allow_saving=False))
        with patch.object(adapter2, "available_tools", return_value=[AddTool()]):
            await adapter2.invoke("are you sure?", prior_trace=run1.trace)
        body3 = json.loads(route.calls[2].request.content)
        for item in body3["input"]:
            print("  continuation input item:", json.dumps(item)[:200])

asyncio.run(main())
```

## 4. `choices[0]` and `stream_chunk_builder` with split choices

Result:

```
split choices -> Kiln sees content: 'Let me add those.' tool_calls: None
stream rebuild: n_choices= 1
   choice 0 content= 'answer' reasoning= 'thinking...'
stream rebuild (tool call on index 1): n_choices= 1
   choice 0 content= 'Let me add.' tool_calls= [ChatCompletionMessageToolCall(function=Function(arguments='{"a":1,"b":2}', name='add'), id='call_1', type='function')] finish= tool_calls
```

```python
"""Offline checks of Kiln adapter behavior relevant to a Responses migration."""
import asyncio
from unittest.mock import patch

import litellm
from litellm.types.utils import ModelResponse, ModelResponseStream

from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties


def make_adapter(model="gpt_5_4", provider=ModelProviderName.openai, thinking="medium"):
    task = datamodel.Task(name="t", instruction="do it")
    rc = KilnAgentRunConfigProperties(
        model_name=model,
        model_provider_name=provider,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
        thinking_level=thinking,
    )
    return LiteLlmAdapter(config=LiteLlmConfig(run_config_properties=rc, additional_body_options={"api_key": "x"}), kiln_task=task)


async def check_split_choices():
    # A reply split into two choices: text in [0], tool call in [1].
    resp = ModelResponse(
        model="gpt-5.4",
        choices=[
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Let me add those."}},
            {"index": 1, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "add", "arguments": "{\"a\":1,\"b\":2}"}}]}},
        ],
    )
    adapter = make_adapter()

    async def fake_acompletion(**kwargs):
        return resp

    with patch("litellm.acompletion", side_effect=fake_acompletion):
        r, choice = await adapter.acompletion_checking_response(model="x", messages=[])
    print("split choices -> Kiln sees content:", repr(choice.message.content), "tool_calls:", choice.message.tool_calls)


def check_stream_rebuild_reasoning_on_index_1():
    chunks = [
        ModelResponseStream(id="r1", model="gpt-5.4", choices=[{"index": 1, "delta": {"role": "assistant", "reasoning_content": "thinking..."}}]),
        ModelResponseStream(id="r1", model="gpt-5.4", choices=[{"index": 0, "delta": {"role": "assistant", "content": "answer"}}]),
        ModelResponseStream(id="r1", model="gpt-5.4", choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]),
    ]
    rebuilt = litellm.stream_chunk_builder(chunks)
    print("stream rebuild: n_choices=", len(rebuilt.choices))
    for c in rebuilt.choices:
        print("   choice", c.index, "content=", repr(c.message.content), "reasoning=", repr(getattr(c.message, "reasoning_content", None)))


async def check_kwargs():
    adapter = make_adapter()
    provider = adapter.model_provider()
    kwargs = await adapter.build_completion_kwargs(provider, [{"role": "user", "content": "hi"}], None)
    shown = {k: v for k, v in kwargs.items() if k not in ("messages", "api_key")}
    print("gpt_5_4/openai kwargs:", shown)
    adapter2 = make_adapter("gpt_5_4_pro", ModelProviderName.openai, "medium")
    print("gpt_5_4_pro litellm id:", adapter2.litellm_model_id())


asyncio.run(check_split_choices())
check_stream_rebuild_reasoning_on_index_1()
import os; os.environ.setdefault("OPENAI_API_KEY", "sk-fake-offline"); asyncio.run(check_kwargs())


def check_stream_rebuild_tool_call_on_index_1():
    chunks = [
        ModelResponseStream(id="r2", model="gpt-5.4", choices=[{"index": 0, "delta": {"role": "assistant", "content": "Let me add."}}]),
        ModelResponseStream(id="r2", model="gpt-5.4", choices=[{"index": 1, "delta": {"role": "assistant", "tool_calls": [
            {"index": 0, "id": "call_1", "type": "function", "function": {"name": "add", "arguments": "{\"a\":1,\"b\":2}"}}]}}]),
        ModelResponseStream(id="r2", model="gpt-5.4", choices=[{"index": 1, "delta": {}, "finish_reason": "tool_calls"}]),
    ]
    rebuilt = litellm.stream_chunk_builder(chunks)
    print("stream rebuild (tool call on index 1): n_choices=", len(rebuilt.choices))
    for c in rebuilt.choices:
        print("   choice", c.index, "content=", repr(c.message.content), "tool_calls=", c.message.tool_calls, "finish=", c.finish_reason)

check_stream_rebuild_tool_call_on_index_1()
```

## 5. Trace validation drops undeclared keys

```python
from pydantic import TypeAdapter
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
ta = TypeAdapter(list[ChatCompletionMessageParam])
print(ta.validate_python([{"role": "assistant", "content": "hi", "reasoning_content": "r",
    "provider_specific_fields": {"reasoning_items": [{"id": "rs_1", "encrypted_content": "abc"}]},
    "kiln_new_field": 1}]))
# -> [{'role': 'assistant', 'content': 'hi', 'reasoning_content': 'r'}]
```
