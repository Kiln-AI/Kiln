---
status: draft
---

# Functional Spec: Code Judge LLM Calls

## 1. Goal

Let a **code judge** (V2 `code_eval`) call an LLM from inside its `score()` function, so it can do cheap deterministic work in code (filter a 1M-token trace down to the few relevant messages) and then hand that small slice to a subjective LLM for judgement. Today a code judge is pure Python with no model access, so any subjective check forces a full LLM-judge over the entire verbose output.

## 2. Approach — reuse the code-tool bridge

A code judge runs in a **spawned, stdlib-only sandbox subprocess** (`adapters/eval/sandbox_worker.py`). It has no API keys, no model adapters, and no event loop, so it cannot call an LLM directly. Reaching an LLM means bridging out of the sandbox to the parent process, which owns the keys and the async model stack.

The just-shipped **`code_tools`** project already built exactly this bridge for nested *tool* calls (`sandbox/tools_api.py` child side; `tools/code_tool.py` parent pump + `_serve`; two queues; dispatcher thread). This project **reuses that bridge** rather than building a judge-specific one:

- Code judges gain the same two-queue bridge and a **`tool_allowlist`** (mirroring code tools), so `score()` code can call `from kiln import tools` / `async_tools`.
- The LLM capability ships as **two new built-in tools** (`llm`, `llm_judge`) selectable in the existing tool picker.
- No new IPC message type, no new synthetic module, no bespoke judge handler. `_serve` / allowlist resolution / `list_tools` / error mapping / recorder / contextvar propagation are reused verbatim.

Consequence (accepted): tools always return a **string**, so structured results come back as a JSON string the author `json.loads` — consistent with the shipped code-tools contract ("results are always `str`").

## 3. The two tools

Both are Kiln built-in tools (`KilnToolInterface`), ids `kiln_tool::llm` and `kiln_tool::llm_judge` (new members of `KilnBuiltInToolId`), resolved through the normal `tool_from_id` path. Both execute **entirely in the parent process**.

### 3.1 `llm` — general-purpose LLM call

Called as `tools.llm(...)`. Parameters (JSON Schema `parameters_schema`):

| Param | Type | Required | Meaning |
|---|---|---|---|
| `prompt` | string | yes | Jinja2 template for the user prompt. |
| `model` | string | yes | Model name (e.g. `gpt-5.5`). |
| `provider` | string | yes | Provider name (e.g. `openrouter`); must be a valid `ModelProviderName`. |
| `input` | object | no | Variables for rendering `prompt` (`{{ user_messages }}`). Defaults to `{}`. |
| `schema` | object | no | JSON Schema for structured output. **Default: none.** |
| `system_prompt` | string | no | Overrides the default judge/eval system prompt. |

Behavior & return (always a string):
- **No `schema`** → returns the model's raw **text**.
- **With `schema`** → returns the structured output **as a JSON string** conforming to `schema`. The author `json.loads` it.

`llm` has no eval coupling — it is a generic "call a model" tool.

### 3.2 `llm_judge` — judge-aware LLM call

Called as `tools.llm_judge(...)`. Same parameters as `llm` **except there is no `schema` param** — the tool automatically applies the **code judge's own eval output-score schema** (`BaseEval.build_score_schema`, the same schema the stock LLM judge uses).

| Param | Type | Required | Meaning |
|---|---|---|---|
| `prompt` | string | yes | Jinja2 template for the user prompt. |
| `model` | string | yes | Model name. |
| `provider` | string | yes | Provider name. |
| `input` | object | no | Template variables. |
| `system_prompt` | string | no | Overrides the default system prompt. |

Behavior & return (always a string):
- Runs the model with the eval's judge schema as structured output, then **maps the result to float scores exactly as the stock LLM judge does** (`pass`→1.0, `fail`→0.0, `critical`→-1.0, 1–5 stars → float; via `build_llm_as_judge_score`).
- Returns those scores **as a JSON string** keyed by the eval's score keys — e.g. `{"consent_present": 1.0}` — so `return json.loads(tools.llm_judge(...))` is a valid `score()` return.

`llm_judge` is **not** the stock judge call: the author supplies the prompt (the stock judge builds its prompt from the eval spec/template), and it deliberately **skips** stock-judge machinery — no judge-result caching, no g-eval/logprob mode, no auto-assembled prompt. It borrows only the **output schema** and the **score mapping**.

Because it needs the eval's schema, `llm_judge` is only meaningful inside a code judge (see §6).

### 3.3 Async mirror

Both tools are available on the async proxy for parallelism: `from kiln import async_tools` then `await async_tools.llm(...)` / `await async_tools.llm_judge(...)`, usable under `asyncio.gather`. This comes for free from the existing bridge mirror; `score()` may be `def` or `async def`.

## 4. Developer experience (examples)

**The motivating case** — filter the trace in code, judge the small slice:

```python
from kiln import tools
import json

PROMPT = """Did the user explicitly consent to deleting the project?
Judge only from these user messages:

{{ user_messages }}
"""

def select_relevant_user_messages(trace):
    ...  # cheap, deterministic filtering

def score(trace):
    msgs = select_relevant_user_messages(trace)
    # llm_judge auto-uses this eval's output schema and returns mapped float scores
    return json.loads(tools.llm_judge(
        prompt=PROMPT,
        input={"user_messages": msgs},
        model="gpt-5.5",
        provider="openrouter",
    ))
```

**Cheap triage, then conditional deeper judge** — mixing `llm` (custom schema) and `llm_judge`:

```python
from kiln import tools
import json

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["safe", "risky"]}},
    "required": ["verdict"],
    "additionalProperties": False,
}

def score(trace):
    msgs = select_relevant_user_messages(trace)
    triage = json.loads(tools.llm(
        prompt="Obviously safe, or worth a closer look?\n{{ msgs }}",
        input={"msgs": msgs},
        model="gpt-5.5-mini", provider="openrouter",
        schema=TRIAGE_SCHEMA,
    ))
    if triage["verdict"] == "safe":
        return {"consent_present": 1.0}
    return json.loads(tools.llm_judge(
        prompt="Carefully verify the user consented.\n{{ msgs }}",
        input={"msgs": msgs},
        model="gpt-5.5", provider="openrouter",   # stronger model only when needed
    ))
```

**Parallel judges** with the async mirror:

```python
from kiln import async_tools
import asyncio, json

async def score(trace):
    msgs = select_relevant_user_messages(trace)
    tone, safety = await asyncio.gather(
        async_tools.llm(prompt=TONE_P,  input={"msgs": msgs}, model="gpt-5.5", provider="openrouter", schema=TONE_SCHEMA),
        async_tools.llm(prompt=SAFE_P, input={"msgs": msgs}, model="gpt-5.5", provider="openrouter", schema=SAFE_SCHEMA),
    )
    ...
```

## 5. Behavior & semantics

- **Parent-side execution (hard invariant).** Both tools run in the main process. The sandbox child never receives API keys, provider config, or the Kiln stack. The child sends `{prompt, model, provider, input, schema?, system_prompt?}` over the bridge; the parent runs the model and returns a string. (Same principle as code_tools: "a code tool never holds an API key.")
- **Prompt rendering.** `prompt` is rendered as a Jinja2 template against `input` **in the parent** (the child has no Jinja). `input` values are inserted as data, not re-rendered, so trace content in `input` cannot inject template syntax. Reuses the existing `_template_env`.
- **Model call.** Reuses the stock LLM-judge execution core: build an ephemeral judge `Task` with the resolved `system_prompt` and (for `llm_judge` / `llm`-with-schema) the `output_json_schema`, then `adapter_for_task(...).invoke_returning_run_output(rendered_prompt)`. `llm` with no schema builds a task with no output schema (free text).
- **Scoring (`llm_judge` only).** Maps structured output to floats via `build_llm_as_judge_score` — identical to the stock judge, guaranteeing parity between a code judge's `llm_judge` call and a plain LLM judge with the same schema.
- **Return type.** Always `str`. Structured output (`llm` w/ schema, and `llm_judge`) is `json.dumps(...)` of the result.

## 6. Selection & availability

- **Allowlist.** Add `tool_allowlist: list[ToolId]` to `CodeEvalProperties` (additive, mirrors `CodeTool`). A code judge's `score()` may call any allowlisted tool over the bridge — MCP tools, RAG, other code tools, and the two new LLM tools.
- **Picker.** `llm` and `llm_judge` are injected as selectable built-in tools in the existing tool picker used to populate the allowlist. No bespoke UI — the same schema-builder/picker experience code tools use.
- **Trust gate.** Unchanged: bridge execution (and therefore any tool call) is gated by the existing code-eval project-trust check. A code judge in an untrusted project skips exactly as it does today.
- **`llm_judge` context.** `llm_judge` needs the eval's score schema. It is resolved through the normal `tool_from_id` path; the eval's schema is supplied at call time via `ToolCallContext` (additive field), which the code-eval adapter's pump populates. Generic tools ignore the field. If `llm_judge` is ever invoked without eval context (e.g. selected by a non-eval agent), it returns a clear error: "`llm_judge` is only available inside a code judge; use `llm` with an explicit schema elsewhere."

## 7. Errors & edge cases

All surface through the existing bridge error mapping — the tool call raises a typed exception (`ToolCallError` / `ToolTimeout` / `ToolNotAllowed`) in the **author's own stack frame**, or the author reads `is_error`. Cases:

- **Invalid `provider`** (not a `ModelProviderName`) or **unknown `model`** → `ToolCallError` with a clear message.
- **Invalid `schema`** (`llm` with a malformed JSON Schema) → `ToolCallError`.
- **Prompt render failure** (undefined Jinja var, bad template) → `ToolCallError` naming the missing key.
- **Structured-output failure** (model returns output that doesn't satisfy the schema after retries) → `ToolCallError`.
- **Model/provider/network error** (rate limit, auth, timeout at the provider) → `ToolCallError` (or `ToolTimeout`) with the underlying message; the author may catch and decide how to score.
- **Nested tool timeout** — if a judge call exceeds the code judge's wall-clock `timeout_seconds`, the whole code-eval invocation times out (existing behavior); the pending call is cancelled.
- **Tool not in allowlist** — `ToolNotAllowed` listing available tool names (existing behavior).
- The author is responsible for their own fallback: an uncaught exception fails the code eval (existing behavior); catching lets them return a degraded score.

## 8. Concurrency, timeouts, limits

- **Wall clock.** The code judge's `timeout_seconds` (`CodeEvalProperties`, default 30, min 1, max 300) bounds the whole invocation including all nested LLM calls, exactly as it bounds nested tool calls for code tools. Authors making one or more LLM calls should raise it. *(Open: whether to raise the default or nudge in-UI when an LLM tool is allowlisted — §12.)*
- **Parallelism.** The parent serves nested calls concurrently (existing pump); the async mirror lets a judge fan out calls under `asyncio.gather`.
- **Process concurrency.** Reuses the existing top-level spawn bound and `_spawn_lock`; no new limits.
- **Cost/scale.** An eval run executes the code judge once per eval item, so each allowlisted LLM call is billed per item × per call. This is the intended trade (small filtered prompt vs. a full-trace judge), but it is real spend and should be visible (§10).

## 9. Security model

- Sandbox stays stdlib-only; no secrets or Kiln stack cross the process boundary.
- All model access is parent-side and subject to the existing trust gate.
- The author controls prompt + model + provider + the data they pass; this is their own eval code, already trusted-to-run. No new secret storage; providers own auth (same as code_tools).

## 10. Observability / cost

Nested LLM calls should be attributable. Minimum: they flow through the existing tool-call recorder (name, args preview, duration, error) already wired in the pump. *(Open: whether to surface token usage / cost and the judge's intermediate output for a code judge's nested calls, and where — §12.)*

## 11. Out of scope (v1)

- Bespoke `from kiln import llm_judge` module / native `str | dict` returns (superseded by the tool approach).
- g-eval / logprob-weighted scoring from code (`llm_judge` is structured-output only).
- Stock-judge caching for author-prompt calls.
- Exposing `llm` broadly in the agent add-tools UI beyond the code-judge/code-tool picker (can follow later; same tool).
- Any change to the stock LLM-judge or code-eval `score()` return contract.
- Injecting the eval schema as a `score()` parameter (`llm_judge` makes it unnecessary).

## 12. Open questions (resolve in architecture)

1. **Code-eval bridge integration.** Migrate the code-eval worker onto the shared `sandbox/worker.py`, or add the bridge to the eval worker by reusing `sandbox/tools_api.py` + an extracted parent pump. (Leaning: extract a shared parent pump from `code_tool.py`; keep the eval worker's `score()`-specific entry + score-dict result.)
2. **Eval-context wiring for `llm_judge`.** Confirm `ToolCallContext` (additive field carrying the eval score schema) vs. eval-aware construction.
3. **Timeout default/UX** when an LLM tool is allowlisted.
4. **Cost/usage surfacing** for nested calls.
5. **`llm_judge` picker scoping** — show it only in the code-judge picker, or everywhere with a clear error off-context.
