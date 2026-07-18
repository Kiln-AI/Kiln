---
status: draft
---

# Architecture: Code Judge LLM Calls

Single-doc architecture — the one novel component (the sandbox bridge) already has a full component design in [`code_tools/components/execution_engine.md`](../code_tools/components/execution_engine.md); this project reuses it and documents only the deltas. Read that doc for bridge internals (queues, dispatcher, IPC protocol, spawn helper).

## 0. Shape of the change

Everything hangs off one move: **give the code-eval sandbox the code-tool bridge**, then ship the LLM capability as two built-in tools.

```
score() in sandbox child ──(requests queue: tool_call)──▶ parent pump ──▶ LlmTool/LlmJudgeTool.run() ──▶ adapter_for_task ──▶ model
        ▲                                                                                                                    │
        └──────────────────────(responses queue: tool_result = str)──────────────────────────────────────────────────────┘
```

The child stays stdlib-only; the model call happens entirely parent-side.

## 1. Data model changes (all additive, zero migration)

### 1.1 `CodeEvalProperties` (`datamodel/eval.py`)

```python
class CodeEvalProperties(BaseModel):
    type: Literal[V2EvalType.code_eval] = V2EvalType.code_eval
    code: str
    reference_keys: list[str] = []
    timeout_seconds: int = Field(default=180, ge=1, le=300)   # was default=30
    tool_allowlist: list[ToolId] = Field(default_factory=list) # NEW
```

- `timeout_seconds` default **30 → 180** (bounds the whole invocation incl. nested LLM calls; max stays 300).
- `tool_allowlist` mirrors `CodeTool.tool_allowlist`, including a `validate_allowlist` model-validator copied from `CodeTool`: reject `SKILL_TOOL_ID_PREFIX` and `KILN_UNMANAGED_TOOL_ID_PREFIX`, reject duplicates. (No self-reference check — a code eval is not itself a tool.)
- Existing `validate_code` is unchanged (still requires a module-level `score`).

### 1.2 `KilnBuiltInToolId` (`datamodel/tool_id.py`)

```python
LLM = "kiln_tool::llm"
LLM_JUDGE = "kiln_tool::llm_judge"
```

Both validate through the existing built-in branch of `_check_tool_id` (membership check) with no new parsing.

### 1.3 `ToolCallContext` (`tools/base_tool.py`)

```python
@dataclass
class ToolCallContext:
    allow_saving: bool = True
    eval_output_schema: str | None = None   # NEW — judge score schema (allow_float_scores=False), JSON string
```

Additive, defaulted. Set only by the code-eval pump; every other caller and tool ignores it. This is the seam that lets `llm_judge` resolve through the generic `tool_from_id` path yet still see the eval's schema at call time.

## 2. The two built-in tools (`tools/built_in_tools/llm_tools.py`, new)

Both subclass `KilnTool` (same pattern as `math_tools.py`): fixed `parameters_schema`, `async run(context, **kwargs) -> ToolCallResult(output=str)`. Both call a shared parent-side helper.

### 2.1 Shared helper — `run_llm_call(...)`

Extracted from `LlmJudgeEval.evaluate` (the non-g-eval path), lives in `tools/built_in_tools/llm_tools.py` (or `adapters/eval/eval_utils/` if we want eval + tools to share it — see §7):

```python
async def run_llm_call(
    *, model: str, provider: str, system_prompt: str | None,
    rendered_prompt: str, output_json_schema: str | None,
) -> RunOutput:
    # validate provider in ModelProviderName -> ValueError
    # build ephemeral _LlmJudgeTask-style Task(instruction=system_prompt, output_json_schema=output_json_schema)
    # structured_output_mode = default_structured_output_mode_for_model_provider(..., disallow function_calling)
    # adapter = adapter_for_task(task, KilnAgentRunConfigProperties(model, provider, SIMPLE, mode),
    #                            AdapterConfig(allow_saving=False, top_logprobs=None))
    # _, run_output = await adapter.invoke_returning_run_output(rendered_prompt)
    # return run_output
```

Reuses the exact machinery `LlmJudgeEval` already uses; `output_json_schema=None` → free-text run (`run_output.output` is `str`); non-None → structured (`run_output.output` is `dict`). No g-eval, no logprobs.

### 2.2 `LlmTool` (`kiln_tool::llm`, name `"llm"`)

`parameters_schema`:

```json
{"type":"object","properties":{
  "prompt":{"type":"string"},"model":{"type":"string"},"provider":{"type":"string"},
  "input":{"type":"object"},"schema":{"type":"object"},"system_prompt":{"type":"string"}},
 "required":["prompt","model","provider"],"additionalProperties":false}
```

`run(context, **kw)`:
1. `rendered = render_prompt(kw["prompt"], kw.get("input") or {})` — `_template_env.from_string(...).render(**input)`; Jinja errors → raise (mapped to `ToolCallError` by the bridge).
2. `schema = kw.get("schema")`; if present, `validate_schema_dict(schema, require_object=True)` → ValueError on malformed. `output_json_schema = json.dumps(schema) if schema else None`.
3. `run_output = await run_llm_call(model=..., provider=..., system_prompt=kw.get("system_prompt"), rendered_prompt=rendered, output_json_schema=output_json_schema)`.
4. Return `ToolCallResult(output = run_output.output if isinstance(str) else json.dumps(run_output.output))`.

### 2.3 `LlmJudgeTool` (`kiln_tool::llm_judge`, name `"llm_judge"`)

Same `parameters_schema` **without `schema`**.

`run(context, **kw)`:
1. `if context is None or context.eval_output_schema is None:` → raise `ValueError("llm_judge is only available inside a code judge; use 'llm' with an explicit schema elsewhere.")` (bridge maps to `ToolCallError`).
2. Render prompt (as above).
3. `run_output = await run_llm_call(..., output_json_schema=context.eval_output_schema)` — the eval's **allow_float_scores=False** schema.
4. `scores = build_llm_as_judge_score(run_output, score_from_token_string)` — identical mapping to the stock judge.
5. Return `ToolCallResult(output = json.dumps(scores))`.

### 2.4 Registry (`tools/tool_registry.py`)

Two new `match` arms returning `LlmTool()` / `LlmJudgeTool()` (no project/task/config needed — everything arrives via kwargs and context).

## 3. Bridge integration (the core work)

### 3.1 Extract a shared parent pump — `tools/sandbox_bridge.py` (new, parent-side)

Today the pump + nested-call server live inside `PythonCodeTool` (`_run_child`, `_serve`, `_build_name_map`, `_get_tools_info`, `_poll_get`, `_close_queues`) and the concurrency primitives are module-level (`_code_tool_depth`, `_get_semaphore`, `CODE_TOOL_MAX_CONCURRENCY`). Extract them into a reusable unit so both `PythonCodeTool` and `CodeEvalAdapter` share one implementation.

```python
# tools/sandbox_bridge.py  (parent-side; may import the Kiln stack — NOT stdlib-only)
CODE_SANDBOX_MAX_CONCURRENCY = 8
_depth: ContextVar[int] = ContextVar("_code_sandbox_depth", default=0)
_semaphore, _semaphore_lock = None, threading.Lock()

@dataclass
class BridgeResult:
    result_msg: dict | None; timed_out: bool; crashed: bool; exit_code: int|None
    stdout: str; stderr: str; duration_ms: int

class NestedToolServer:
    """Owns allowlist resolution + _serve for one bridged run."""
    def __init__(self, allowlist: list[ToolId], project: Project, task: Task | None,
                 context: ToolCallContext | None, recorder=None): ...
    async def serve(self, msg: dict, responses: Queue) -> None:   # == today's _serve, verbatim logic
    async def name_map(self) -> dict[str, list[ToolId]]: ...
    async def tools_info(self) -> list[dict]: ...

async def run_bridged_child(*, target, args, timeout_s: float,
                            requests: Queue, responses: Queue,
                            server: NestedToolServer) -> BridgeResult:
    """Spawn target(*args, requests, responses); pump requests; serve tool_call/list_tools
    via server; return on the first 'result' message (raw msg), timeout, or crash.
    Depth cap (>=10 -> error), semaphore acquired only at depth 0. Verbatim port of
    PythonCodeTool._run_child, minus result interpretation."""
```

`PythonCodeTool` becomes a thin caller: builds a `NestedToolServer` (its allowlist, project, task, `ToolCallContext(allow_saving=...)`, recorder), calls `run_bridged_child(target=child_main, args=(code, kwargs))`, then maps `BridgeResult.result_msg` → `ChildOutcome` → `ToolCallResult` exactly as today. **No behavioral change to code tools** — this is a pure refactor guarded by the existing `sandbox/test_code_tool_execution.py` suite.

### 3.2 Code-eval child worker → two queues (`adapters/eval/sandbox_worker.py`)

Convert `run_scorer`'s child from one result queue to the bridge protocol:

```python
def execute_scorer_bridged(code, inputs, requests: Queue, responses: Queue) -> None:
    # redirect stdout/stderr (existing)
    install_tools_modules(requests, responses)      # <-- REUSED from sandbox/tools_api.py
    namespace = {}; exec(compile(code, "<code_eval>", "exec"), namespace)
    score_fn = namespace.get("score")               # existing checks: defined/callable/accepts output|trace
    call_kwargs = {declared params from output/trace/reference_data/task_input}   # existing logic
    result = call_entrypoint(score_fn, call_kwargs) # existing (sync/async)
    requests.put({"type":"result","ok":result,"stdout":...,"stderr":...})   # ok = scores DICT (not serialized)
    # exceptions -> requests.put({"type":"result","error":...,"traceback":...,...})
```

Key differences from the code-tool child (`sandbox/worker.py`): entry point `score` (not `run`), the param-injection signature logic, and `ok` carries the **scores dict** verbatim (a code eval returns a dict, not a passthrough string — no `_serialize_result`). Everything else (bridge install, stdout capture, traceback trim) mirrors the code-tool child. The old single-queue `run_scorer` is removed; its callers move to the pump.

### 3.3 `CodeEvalAdapter.evaluate` hosts the pump (`adapters/eval/v2_eval_code_eval.py`)

```python
async def evaluate(self, eval_input):
    # trust gate unchanged (skip if project untrusted)
    inputs = {output, trace, reference_data, task_input}   # existing
    server = NestedToolServer(
        allowlist=props.tool_allowlist, project=project, task=self.target_task,
        context=ToolCallContext(allow_saving=False,
                                eval_output_schema=BaseEval.build_score_schema(self.eval, allow_float_scores=False)),
        recorder=None,
    )
    ctx = multiprocessing.get_context("spawn"); requests, responses = ctx.Queue(), ctx.Queue()
    res = await run_bridged_child(target=execute_scorer_bridged, args=(props.code, inputs),
                                  timeout_s=float(props.timeout_seconds),
                                  requests=requests, responses=responses, server=server)
    if res.timed_out: raise RuntimeError(f"Code eval scorer timed out after {props.timeout_seconds}s")
    if res.crashed:   raise RuntimeError(f"Scorer crashed (exit code {res.exit_code})")
    msg = res.result_msg
    if "error" in msg: raise RuntimeError(f"Code eval scorer failed: {msg['error']}\n{msg.get('traceback','')}")
    raw = msg["ok"]                                   # scores dict
    if not isinstance(raw, dict): raise RuntimeError(...)
    return V2EvalResult(scores=self._validate_scores(raw))
```

`_validate_scores` (key-set match, bool/int→float coercion) is unchanged.

### 3.4 Concurrency: delete `_code_eval_execution_lock`

Today `v2_eval_code_eval.py` serializes **all** code evals through a single `asyncio.Lock`. That is removed; code evals now run through `run_bridged_child`, which acquires the shared bounded semaphore (`CODE_SANDBOX_MAX_CONCURRENCY = 8`) at depth 0 — the same pool code tools use. This is both **required** (a global lock + LLM latency would serialize every eval item behind one judge call) and a **latency win** (up to 8 concurrent code-eval sandboxes instead of 1). The `_spawn_lock` in `sandbox/spawn.py` still serializes only `p.start()` (sub-ms), shared across both paths.

## 4. UI changes (`app/web_ui`)

- **Allowlist picker** in `components/eval_types/code_eval_form.svelte`: add the same tool-picker used by the code-tool create/edit page, bound to `properties.tool_allowlist`. Reuse the component wholesale.
- **Inject the two built-ins into the picker catalog** so `llm` and `llm_judge` are selectable. `llm_judge` is offered only in the code-eval picker context (it errors off-context); `llm` may appear generally.
- **Editor examples** in `components/eval_types/code_eval_helpers.ts`: add one or two `generate_examples` entries showing `tools.llm_judge(...)` and the cheap-triage pattern. These strings are mirrored byte-for-byte and executed by `test_code_eval_samples.py` — update that fixture in lockstep (see §6).
- Regenerate the OpenAPI client (`generate_schema.sh`) for the new `tool_allowlist` field.

## 5. Error handling

All nested-call errors already funnel through the bridge's typed mapping (`ToolNotAllowed`/`ToolTimeout`/`ToolCallError`) raised in the author's frame, per `sandbox/tools_api.py`. New surfaces map as:

| Failure | Where | Result |
|---|---|---|
| bad provider / unknown model | `run_llm_call` → ValueError | `ToolCallError` in author frame |
| malformed `schema` (llm) | `validate_schema_dict` → ValueError | `ToolCallError` |
| Jinja render error | `render_prompt` → UndefinedError/JinjaExtractionError | `ToolCallError` naming the missing key |
| structured-output parse fail | adapter / `build_llm_as_judge_score` → ValueError | `ToolCallError` ("LLM failed to follow the schema") |
| provider network/auth/rate error | adapter raises | `ToolCallError` (or `ToolTimeout`) with underlying message |
| `llm_judge` off-context | `run()` ValueError | `ToolCallError` (clear guidance message) |
| whole-judge over `timeout_seconds` | pump deadline | code-eval raises RuntimeError (skips/fails the item as today) |

`_serve` already wraps its body in try/except → `call_error`, so a raising tool never hangs the child. Authors may `try/except` these in `score()` to return a degraded score.

## 6. Testing strategy

- **Datamodel** (`test_phase4_data_model.py` peers): `tool_allowlist` validation (skill/unmanaged/dupe rejection), new timeout default, `KilnBuiltInToolId` round-trips, `ToolCallContext` default.
- **Built-in tools** (new `test_llm_tools.py`, fake adapter double): `llm` text vs schema→JSON-string; `llm_judge` maps pass/fail/critical/1-5 → float and returns JSON scores; off-context error; provider/model/schema/render errors; parity — `llm_judge` output equals a stock `LlmJudgeEval` run for the same schema+prompt.
- **Bridge refactor** (existing `sandbox/test_code_tool_execution.py`): must stay green unchanged — proves the extraction is behavior-preserving for code tools. Add an identity assertion that code tools and code evals share one `_spawn_lock` and one semaphore.
- **Code-eval bridge** (real spawns, `test_v2_eval_code_eval.py` / `test_sandbox_worker.py` style): `score()` calls `tools.llm_judge` / `tools.llm` (fake tool double routed through `_serve`), sync and `async def score` with `asyncio.gather`; allowlist enforcement (`ToolNotAllowed`); timeout kills a child mid-LLM-call; concurrency — N code evals run in parallel (regression against the deleted global lock); trust-refusal short-circuits before spawn.
- **Samples** (`test_code_eval_samples.py`): mirror the new `code_eval_helpers.ts` example strings and execute them through the real sandbox with a stubbed judge tool.
- **UI** (`code_eval_form.test.ts`): allowlist picker binds; `llm`/`llm_judge` selectable; example snippets present.

## 7. Open decisions (small)

1. **Home of `run_llm_call`.** Either `tools/built_in_tools/llm_tools.py` or a shared `adapters/eval/eval_utils/` module so `LlmJudgeEval` can also adopt it. Leaning: put it beside the tools, and optionally refactor `LlmJudgeEval`'s non-g-eval path onto it in a later cleanup (not required for v1).
2. **Cost/usage surfacing.** v1: nested calls flow through the existing recorder (name/args/duration/error). Surfacing token cost + the judge's intermediate output per code-eval item is deferred; `run_output.intermediate_outputs` is available if we later want it.
3. **`llm` general availability.** v1 exposes both tools in the code-eval picker; whether `llm` also lands in the general agent add-tools UI is a one-line catalog change deferred to a follow-up.

## 8. Component-design decision

Single `architecture.md` (this doc). No separate `components/` files: the only deep component (the sandbox bridge) is fully specified in `code_tools/components/execution_engine.md`, and this project's novelty is integration + two small tools, all captured above.
