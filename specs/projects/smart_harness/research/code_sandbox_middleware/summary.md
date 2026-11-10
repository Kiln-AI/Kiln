# Research: Middleware-Style Code in the Existing Code Sandbox

Explored 2026-11-10 at repo commit `57c7c126`. The question: if a middleware is Python code, what does the sandbox that runs code tools and code judges already give us, and what is missing? Three shapes were run for real through `run_bridged_child`, the same call a code tool uses.

## How the sandbox works

- **One process per run.** The parent spawns a fresh Python process (`multiprocessing` spawn) for each run, `exec`s the code, and calls a module-level `run(**kwargs)`, sync or async (`libs/core/kiln_ai/sandbox/worker.py`, `sandbox/entrypoint.py`). The kwargs must be JSON-serializable.
- **Return value.** `run` returns a `str`, or a dict/list/number/bool/None that is JSON-encoded. Anything else is an error. stdout and stderr are captured.
- **Calling out.** Inside the code, `from kiln import tools` gives `tools.<name>(**kwargs)`. The call goes over a queue to the parent, which checks the name against the run's allowlist of tool IDs, validates the arguments against the tool's schema, runs the tool **in the parent process**, and sends back the tool's output **as a string** (`libs/core/kiln_ai/tools/sandbox_bridge.py:179-381`, `sandbox/tools_api.py`). `kiln.async_tools` is the awaitable version, so `asyncio.gather` runs calls in parallel.
- **Errors.** Nested call failures raise `ToolNotAllowed`, `ToolTimeout` or `ToolCallError` in the code.
- **Limits.** One wall-clock timeout covers the whole run, nested calls included. Nesting depth is capped at 10. At most 16 top-level runs at once across the process.
- **Where it runs.** A local child process of whatever process imports `kiln_ai`: the desktop app, or a plain script or server using the library. The code tools spec's "Desktop-only, forever" rules out Kiln's own hosted servers, not the library. The trust check applies only in the desktop API when saving or testing code.
- **Not a security boundary.** The child has the same access to files, network and imports as its parent. The isolation is for timeouts and crashes.
- **Testing.** `libs/core/kiln_ai/tool_testing/` gives authors a pytest fixture with a fake `kiln.tools`, so code that calls tools can be unit-tested without the sandbox.

## What code can already call

| Call from code | What it is | Notes |
|---|---|---|
| `tools.llm(model=, provider=, prompt=, input=, system_prompt=, schema=)` | Built-in tool `kiln_tool::llm` (`libs/core/kiln_ai/tools/built_in_tools/llm_tools.py`). One model call with an inline prompt and an optional inline JSON schema. No saved task: it builds a throwaway task and runs it through `adapter_for_task`. | Because it goes through `adapter_for_task`, a Jev model works too. Returns the output only. Nothing is saved (`allow_saving=False`). |
| `tools.<task_tool_name>(input=...)` | A saved Kiln task plus a saved run config, wrapped as a `kiln_task::` tool (`libs/core/kiln_ai/tools/kiln_task_tool.py`). | The inner run is saved in that task's dataset when saving is allowed. Returns the output only. |
| `tools.<any other allowlisted tool>(...)` | MCP tools, RAG search tools, other code tools, memory tools. | A nested code tool is another process. |

## Prototype results

One policy was written three ways. Each run received `messages` and `turn_number` as kwargs and returned a JSON action (`respond`, or `continue` with optional overrides). Nothing in Kiln acts on that return value yet; the prototype only shows the code side.

| Shape | Worked? | Time | What came back |
|---|---|---|---|
| 1. Inline LLM call (`tools.llm`, `gpt_4_1_nano` on OpenRouter) | Yes. All three test messages were classified correctly. | About 1.0 s per call (3.9 s for the first). Sandbox overhead about 80 ms. | The JSON values only. |
| 2. Inline Jev call (same tool, `model="jev_1_13"`, `provider="typesafe"`; Jev's HTTP client was faked, since there is no TypeSafe key here) | Yes. The call reached the Jev adapter, which turned the inline schema into one request with two questions. | Sandbox overhead about 77 ms. Jev latency not measured. | The JSON values only. The fake answered `hours` at probability 0.94 and `needs_smart_model` at 0.04; the code received `"hours"` and `false`. |
| 3. Saved Kiln task (`tools.support_triage(input=...)`) | Yes. | About 1.1–1.5 s per call. Sandbox overhead about 80 ms. | The JSON values only. Three runs were saved in the triage task's dataset, tagged `tool_call`, each with tokens and cost. |

## Library check

An agent task with one code tool in its tool list was run from a plain Python script with `adapter_for_task(...).invoke(...)`: no desktop app, no API server. The model called the tool, the code ran in a child process (a different pid from the script), and the model answered from the result. Code tools work in the library today.

## Gaps for middleware use

1. **Nothing acts on the result.** The harness has no code that takes "respond", "call this tool" or "use these settings" from a code run and applies it to the turn. This is the main new work, and it is the same work whatever form a middleware takes.
2. **Probabilities are dropped twice.** `LlmTool.run` returns only `run_output.output`, and the bridge returns only `result.output`. Jev's probabilities and confidence never reach the code. With a saved task they are stored on the inner run's `intermediate_outputs`, but the code still does not get them.
3. **Cost is not reported.** The inline `llm` tool discards usage. A task tool records usage on the inner run only. The turn that triggered the call does not include either.
4. **Inline calls leave no record.** Nothing about an inline call is saved on the run. A code tool resolved from the registry is built without a call recorder.
5. **No way to continue the turn and see the result.** There is no `next()`. Code can decide before the model runs, but cannot run the model and then check or replace its answer.
6. **The inline tool is narrow.** It takes one rendered prompt string. No message list, no temperature, no thinking level, no tools.
7. **A saved task needs a wrapper.** Calling a task requires a `kiln_task` tool server object for that task and run config, and its tool ID on the allowlist.
8. **No memory between turns.** Every run is a fresh process. Anything carried across turns has to be passed in by the harness.
9. **16 at a time.** Evals run many turns in parallel and would share the cap with code tools and code judges.
10. **Needs process spawning with queues.** The sandbox uses `multiprocessing` spawn and `multiprocessing.Queue`. Hosts that restrict those would not run it. No such host was tested.

## Appendix: prototype script

Run from the repo root with `uv run python <path>`. It reads the OpenRouter key from `OPENROUTER_QA_KEY` and sets it in-process only.

```python
"""Prototype: middleware-style code running in Kiln's real code sandbox.

Three shapes, each run through run_bridged_child exactly as a code tool runs:
  1. inline LLM call via the built-in `llm` tool (no task)
  2. inline Jev call via the same tool (Jev HTTP client faked: no TypeSafe key here)
  3. calling a saved Kiln task (task + run config wrapped as a kiln_task tool)
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ["OPENROUTER_API_KEY"] = os.environ["OPENROUTER_QA_KEY"]  # in-process only
os.environ.setdefault("TYPESAFE_API_KEY", "fake-key")

from kiln_ai.adapters.jev import JevClient  # noqa: E402
from kiln_ai.adapters.jev.jev_jsonschema import (  # noqa: E402
    ChoiceAnswer,
    NoulAnswer,
    SystemOneResponse,
    SystemOneUsage,
)
from kiln_ai.datamodel.datamodel_enums import (  # noqa: E402
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.external_tool_server import (  # noqa: E402
    ExternalToolServer,
    ToolServerType,
)
from kiln_ai.datamodel.project import Project  # noqa: E402
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties  # noqa: E402
from kiln_ai.datamodel.task import Task, TaskRunConfig  # noqa: E402
from kiln_ai.sandbox.worker import child_main  # noqa: E402
from kiln_ai.tools.base_tool import ToolCallContext  # noqa: E402
from kiln_ai.tools.sandbox_bridge import NestedToolServer, run_bridged_child  # noqa: E402

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["hours", "greeting", "other"],
            "description": "What the message is about. 'hours' = asking for opening hours only. 'greeting' = only a hello with no question. 'other' = anything else.",
        },
        "needs_smart_model": {
            "type": "boolean",
            "description": "True if answering needs multi-step reasoning or calculation.",
        },
    },
    "required": ["intent", "needs_smart_model"],
    "additionalProperties": False,
}

# The same policy body is used in all three shapes. Only `decide()` differs.
POLICY = '''
CANNED = {
    "hours": "We're open 9am-5pm, Monday to Friday.",
    "greeting": "Hi! I can help with orders, billing and returns.",
}

def run(messages, turn_number):
    last_user = [m for m in messages if m["role"] == "user"][-1]["content"]
    d = decide(last_user)
    if d["intent"] in CANNED:
        return {"action": "respond", "text": CANNED[d["intent"]], "decision": d}
    if d["needs_smart_model"]:
        return {"action": "continue", "overrides": {"model_name": "claude_opus", "thinking_level": "high"}, "decision": d}
    return {"action": "continue", "decision": d}
'''

INLINE_LLM = (
    '''
import json
from kiln import tools

SCHEMA = __SCHEMA__

def decide(message):
    raw = tools.llm(
        model="gpt_4_1_nano",
        provider="openrouter",
        system_prompt="You classify one message sent to a store's support agent.",
        prompt="Message:\\n{{ message }}",
        input={"message": message},
        schema=SCHEMA,
    )
    return json.loads(raw)
'''
    + POLICY
)

INLINE_JEV = INLINE_LLM.replace('"gpt_4_1_nano"', '"jev_1_13"').replace(
    '"openrouter"', '"typesafe"'
)

VIA_TASK = (
    '''
import json
from kiln import tools

def decide(message):
    return json.loads(tools.support_triage(input=message))
'''
    + POLICY
)

MESSAGES = [
    "what time do you open?",
    "yo",
    "My order arrived broken twice and I was charged 3 times at 2 different prices. Work out what refund I'm owed under a 15% restocking fee.",
]


async def run_policy(code, message, allowlist, project=None, task=None):
    calls = []
    server = NestedToolServer(
        allowlist=allowlist,
        project=project,
        task=task,
        context=ToolCallContext(allow_saving=True),
        recorder=calls.append,
    )
    start = time.perf_counter()
    result = await run_bridged_child(
        target=child_main,
        args=(code, {"messages": [{"role": "user", "content": message}], "turn_number": 1}),
        timeout_s=60.0,
        server=server,
    )
    total_ms = round((time.perf_counter() - start) * 1000)
    msg = result.result_msg or {}
    nested_ms = sum(c.duration_ms for c in calls)
    if "ok" in msg:
        out = json.loads(msg["ok"])
        print(f"  {message[:42]!r:46} -> {out['action']:8} decision={out['decision']} overrides={out.get('overrides')}")
    else:
        print(f"  {message[:42]!r:46} -> ERROR {msg.get('error')}")
    print(f"      total {total_ms} ms; nested calls {[(c.tool_name, c.duration_ms) for c in calls]}; sandbox overhead ~{total_ms - nested_ms} ms")
    return calls


async def fake_system_one(self, request):
    print(f"      [fake Jev] state keys={list(request.state.keys()) if isinstance(request.state, dict) else type(request.state)}; questions={request.model_dump(exclude_none=True).get('questions')}"[:900])
    return SystemOneResponse(
        model="jev-1.13.0",
        answers={
            "intent": ChoiceAnswer(type="choice", choice="hours", confidence=0.93, probabilities={"hours": 0.94, "greeting": 0.01, "other": 0.05}),
            "needs_smart_model": NoulAnswer(type="noul", noul=0.04),
        },
        usage=SystemOneUsage(input_tokens=90, output_tokens=6),
    )


async def main():
    schema_src = repr(TRIAGE_SCHEMA).replace("True", "True").replace("False", "False")

    print("== 1. inline LLM call (built-in `llm` tool, no task) ==")
    for m in MESSAGES:
        await run_policy(INLINE_LLM.replace("__SCHEMA__", schema_src), m, ["kiln_tool::llm"])

    print("== 2. inline Jev call (same tool; Jev HTTP faked) ==")
    with patch.object(JevClient, "system_one", fake_system_one):
        await run_policy(INLINE_JEV.replace("__SCHEMA__", schema_src), MESSAGES[0], ["kiln_tool::llm"])

    print("== 3. calling a saved Kiln task ==")
    with tempfile.TemporaryDirectory() as tmp:
        project = Project(name="proto", path=Path(tmp) / "project.kiln")
        project.save_to_file()
        task = Task(
            name="support_triage",
            instruction="You classify one message sent to a store's support agent.",
            output_json_schema=json.dumps(TRIAGE_SCHEMA),
            parent=project,
        )
        task.save_to_file()
        run_config = TaskRunConfig(
            name="nano",
            parent=task,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt_4_1_nano",
                model_provider_name=ModelProviderName.openrouter,
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
        )
        run_config.save_to_file()
        server = ExternalToolServer(
            name="support_triage",
            type=ToolServerType.kiln_task,
            description="Classify a support message",
            properties={
                "name": "support_triage",
                "description": "Classify a support message",
                "task_id": task.id,
                "run_config_id": run_config.id,
                "is_archived": False,
            },
            parent=project,
        )
        server.save_to_file()
        tool_id = f"kiln_task::{server.id}"
        with patch("kiln_ai.tools.kiln_task_tool.project_from_id", return_value=project):
            for m in MESSAGES:
                await run_policy(VIA_TASK, m, [tool_id], project=project, task=None)
        runs = task.runs()
        print(f"  saved runs in the triage task's dataset: {len(runs)}")
        if runs:
            r = runs[0]
            print(f"  first saved run: tags={r.tags} source={r.input_source.type if r.input_source else None} usage={r.usage.model_dump(exclude_none=True) if r.usage else None}")


if __name__ == "__main__":
    asyncio.run(main())
```
