---
status: complete
---

# Architecture: Code Tools

Technical design for [functional_spec.md](functional_spec.md) / [ui_design.md](ui_design.md). Target: `Kiln-AI/kiln`, branched off `scosman/evals_v2`. File paths verified against that branch (head `76f56b8`). Assumes the **async-`score` eval fix** (handed off separately) has landed on the branch; nothing here breaks if it lands in either order, since the shared helper subsumes it.

Structure: this doc + one component doc for the only novel piece, the **execution engine** (sandbox worker + nested tool-call IPC): [components/execution_engine.md](components/execution_engine.md). Everything else follows well-worn kiln patterns and is fully specified here.

## 1. System overview

```
agent loop (LiteLlmAdapter.process_tool_calls)          test endpoint (code_tool_api.py)
        │  schema-validates args, asyncio.gather                │ transient CodeTool, persist nothing
        ▼                                                       ▼
   PythonCodeTool.run(context, **kwargs)      ◄── tools/code_tool.py (parent-side, heavy imports OK)
        │ trust check → depth check → semaphore (top-level only)
        │ spawn child (shared _spawn_lock + __main__ stub swap)
        ▼
   child process: kiln_ai/sandbox/worker.py   ◄── stdlib-only; injects `kiln.tools` / `kiln.async_tools`
        │ exec(code) → run(**kwargs)   [sync or async — shared call_entrypoint helper]
        │      │ tools.get_user(id=…)  ──┐
        │      ▼                         │ IPC request queue
        │  blocks on per-call event      ▼
        │                     parent message pump: resolve name against allowlist
        │                        → tool_from_id_and_project(...)  → await tool.run(ctx, **kw)
        │      ◄─────────────────  IPC response queue (result str | not_allowed | error)
        ▼
   {"type":"result", ok|error, stdout, stderr}  → ToolCallResult / TestCodeToolResponse
```

## 2. File inventory

### Library — `libs/core/kiln_ai`

| File | Change |
|---|---|
| `datamodel/code_tool.py` | **New.** `CodeTool(KilnParentedModel)` (§3). |
| `datamodel/project.py` | Add `"code_tools": CodeTool` to `Project.parent_of`. |
| `datamodel/__init__.py` | Export `CodeTool`. |
| `datamodel/tool_id.py` | `CODE_TOOL_ID_PREFIX = "kiln_tool::code::"`, `build_code_tool_id(id)`, `code_tool_id_from_tool_id(id)` (RAG-helper pattern), branch in `_check_tool_id`. |
| `sandbox/` | **New stdlib-only package** (empty `__init__.py`): `spawn.py` (shared `_spawn_lock` + `__main__`-stub spawn helper), `entrypoint.py` (`call_entrypoint(fn, kwargs)` — sync call + `asyncio.run` when the result is a coroutine; the same logic the eval async fix introduces), `worker.py` (child entry for code tools), `tools_api.py` (synthetic `kiln.tools` / `kiln.async_tools` modules, typed exceptions, child-side bridge). Top-level placement is deliberate: `kiln_ai/__init__.py` is a docstring, so a spawn child importing `kiln_ai.sandbox.worker` pulls in nothing heavy. (`kiln_ai.tools.__init__` eagerly imports the registry — unusable in the child; `kiln_ai.adapters.__init__` is lazy for exactly this reason.) |
| `adapters/eval/sandbox_worker.py` | **Mechanical refactor only** (confirmed in scope): the inline `_spawn_lock` + stub-swap block delegates to `sandbox/spawn.py`, and the scorer call delegates to `sandbox/entrypoint.py`. The lock **must be process-global across both features** — two locks reintroduces PyInstaller bug #7410 exposure. Public `run_scorer()` API and behavior unchanged; the full existing eval test suite (incl. the async-`score` tests from the separate fix, and `test_sandbox_worker_perf.py`) must pass unchanged. No other eval changes — code-eval endpoints/policies are out of scope. |
| `tools/code_tool.py` | **New.** `PythonCodeTool(KilnToolInterface)` — parent-side runtime (§4 + component doc). |
| `tools/tool_registry.py` | New branch for `CODE_TOOL_ID_PREFIX`; refactor to expose `tool_from_id_and_project(tool_id, project, task=None)` with `tool_from_id(tool_id, task)` as the existing thin wrapper (needed so the test endpoint and the nested-call dispatcher can resolve tools without a `Task`). `tool_from_id` behavior unchanged. |

Trust enforcement imports `is_code_eval_trusted` from `v2_eval_code_eval` at the three call sites described in §5.2. Import-time trust is enforced via the `trusted` parameter on the import/sync endpoints (§5.1).

### Desktop — `app/desktop/studio_server`

| File | Change |
|---|---|
| `code_tool_api.py` | **New.** `connect_code_tool_api(app)` with the endpoints in §6; wired into `desktop_server.py`. |
| `tool_api.py` | `available_tools` gains a `ToolSetType.CODE` group listing non-archived code tools (`id=build_code_tool_id(ct.id)`, `name=ct.tool_function_name`, `description=ct.tool_description`). |

### Web UI — `app/web_ui` (structure in [ui_design.md](ui_design.md))

New: `routes/(app)/tools/[project_id]/add_tools/code_tool/+page.svelte` (two-step wizard, `pushState` steps), `routes/(app)/tools/[project_id]/code_tools/[code_tool_id]/+page.svelte` (detail), shared `code_tool_test_panel.svelte`, `code_tool_helpers.ts` (typed placeholder codegen, examples, import-helper), API wrappers `lib/api/code_tool_api.ts`. Changed: `add_tools/+page.svelte` (suggested card — removing Control GitHub — + custom card), `tools/[project_id]/+page.svelte` (code-tool rows in the existing table, Type "Code Tool", Status "Ready"/"Archived"), type-formatter mapping. Regenerate `api_schema.d.ts`.

## 3. Datamodel — `CodeTool`

```python
class CodeTool(KilnParentedModel):
    # editable metadata (the only fields any API mutates post-create)
    name: FilenameString                       # user-facing display name (folder naming)
    description: str | None = None             # user-facing notes; P2 — cut if unneeded (never shown to models)
    is_archived: bool = False
    # functional content — immutable post-create (enforced at the API layer, §6)
    tool_function_name: str                    # ^[a-z][a-z0-9_]{0,63}$ (field validator; mirrors UI tool_name_validator)
    tool_description: str = Field(min_length=1)  # shown to agents
    parameters_schema: dict[str, Any]          # validate_schema_dict(v, require_object=True)
    code: str
    timeout_seconds: int = Field(default=60, ge=1)   # no max (locked)
    tool_allowlist: list[ToolId] = Field(default_factory=list)
```

Model validators (run on every construction/deserialization — create, test, file-load all validate identically, the `CodeEvalProperties` pattern):

1. **Code trio** (adapted from `CodeEvalProperties.validate_code`, filename `"<code_tool>"`): ≤ 64 KB UTF-8; `compile(...)`; AST scan of top-level nodes for a function named `run` — **`FunctionDef` or `AsyncFunctionDef`, both valid** (both executable, §3.1 of the functional spec).
2. **Allowlist**: reject skill IDs and unmanaged IDs with targeted messages; reject duplicates; reject `build_code_tool_id(self.id)` (self-reference — `id` exists at construction).

Storage: `{project}/code_tools/{id} - {name}/code_tool.kiln`, code inline in the JSON. Purely additive — no migration; old app versions never scan unknown child folders.

**Immutability is an API contract, not a datamodel mechanism** (confirmed): the Pydantic model stays plain-mutable like every Kiln model (field-freezing fights the load/save machinery); no endpoint mutates functional fields (§6). `tool_function_name` uniqueness among non-archived siblings is likewise API-enforced — model-level cross-sibling checks would break file loads.

## 4. Runtime tool — `PythonCodeTool` (parent side)

```python
class PythonCodeTool(KilnToolInterface):
    def __init__(self, code_tool: CodeTool, project: Project, task: Task | None = None,
                 tool_call_recorder: Callable[[ToolCallLogEntry], None] | None = None): ...
    async def id(self) -> ToolId            # build_code_tool_id(code_tool.id)
    async def name(self) -> str             # code_tool.tool_function_name
    async def description(self) -> str      # code_tool.tool_description
    async def toolcall_definition(self) -> ToolCallDefinition   # name/tool_description/parameters_schema
    async def run(self, context: ToolCallContext | None = None, **kwargs) -> ToolCallResult
```

`run()` orchestration (full pseudocode + IPC protocol in the [component doc](components/execution_engine.md)):

1. **Trust check**: `is_code_eval_trusted(str(project.path))` — untrusted → `ToolCallResult(is_error=True, ...)` per the functional-spec error table; never executes. Desktop-only enforcement rides on trust never being granted server-side.
2. **Depth check**: contextvar `_code_tool_depth`; at entry, `depth >= 10` → error result ("max code tool depth exceeded — check for a cycle"); else set `depth + 1` for the run's scope (token reset in `finally`). Nested code tools dispatched from this run's message pump inherit the incremented value through the async context.
3. **Semaphore — top-level only**: module-level bounded `asyncio.Semaphore(8)` (library constant, lazily created inside the running loop), acquired **only when `depth == 0`**. Nested executions bypass it — counting them deadlocks the pool (parents hold slots while blocked on children). Worst case 8 × 10 processes.
4. **Execute**: spawn child + pump messages until result/timeout (component doc).
5. **Map outcome** to `ToolCallResult` per functional spec §2.4; success output passes through the child's serialized string (§2.3 rules applied child-side).

Nested-call dispatch (the message pump's `tool_call` handler):

- **Name→ToolId map** built lazily on first nested call, from local data only — MCP: last ID segment; RAG: `rag_config.tool_name`; kiln_task: server properties `name`; code: `tool_function_name`; built-ins: known constants. No network.
- No match → `not_allowed` reply (lists available names). Two matches → `call_error` "ambiguous".
- Resolve via `tool_from_id_and_project(tool_id, project, task)`; validate kwargs against the tool's `toolcall_definition()` parameters (`validate_schema_with_value_error` — exactly what the adapter does for model-issued calls) → invalid: `call_error`.
- `await tool.run(ToolCallContext(allow_saving=<inherited>), **kwargs)` inside `asyncio.create_task` — concurrent nested calls run concurrently; agent-run contextvars propagate (MCP sessions reused; nested code tools see the depth var).
- Reply: success → raw output string, **passed through verbatim — no parsing** (string-returns decision); `is_error=True` → kind `timeout` when identifiable (nested code-tool timeout / `asyncio.TimeoutError`), else `call_error` with `.raw = output`.
- `tool_call_recorder` (test endpoint) records `{tool_name, arguments, output_preview (1 KB), is_error, duration_ms}`.

## 5. Trust gate — two complementary layers

Per functional spec §5, trust enforcement uses two layers:

### 5.1 Import-time project trust gate (Phase 6)

- `POST /api/import_project` gains a `trusted: bool = False` query param; returns HTTP 400 when false/missing.
- `POST /api/git_sync/save_config`'s `SaveConfigRequest` gains a `trusted: bool = False` body field; returns HTTP 400 when false/missing.
- Both use the same error message: "Import cancelled: you must confirm you trust this project before importing. Kiln projects can contain code that runs on your machine."
- Frontend: `import_project.svelte` inserts a trust interstitial page for both import flows. For local file import, the page appears after the path is entered. For the git wizard, the page appears immediately after URL validation / credential entry, **before** any clone or local write (step order: url -> credentials -> trust -> branch -> project -> complete). The page uses the warning exclaim-circle SVG icon, title "Trust this Project?", and [Cancel]/[Trust Project] buttons. Only on [Trust Project] does the flow proceed with `trusted=true`.

### 5.2 Session-scoped code-execution trust (Phases 2–6)

Three call sites import `is_code_eval_trusted`:
1. `PythonCodeTool.run()` — untrusted returns `ToolCallResult(is_error=True)`.
2. Test endpoint (`test_code_tool`) — untrusted returns `{not_trusted: true}` (200).
3. Create endpoint (`create_code_tool`) — untrusted returns `{not_trusted: true}` (200), preventing persistence without trust.

The UI trust dialog is factored into a shared `CodeTrustDialog` component (`lib/components/code_tools/code_trust_dialog.svelte`) used by both the test panel and the create wizard. On trust grant (via `grantCodeEvalTrust`), the dialog retries the operation.

All trust-related strings have been human-reviewed and approved.

## 6. API — `code_tool_api.py`

All tagged `Code Tools`. Agent policies use the existing `x-agent-policy` machinery (`kiln_server/utils/agent_checks/policy.py`). All approval strings have been human-reviewed and approved. Code-eval endpoints are untouched.

| Endpoint | Method | Agent policy | Notes |
|---|---|---|---|
| `POST …/create_code_tool` | POST | `agent_policy_require_approval("Allow agent to create and save a code tool (Python that runs on your machine)?")` | Full field set. Construct with `parent=project` (validators run), enforce `tool_function_name` uniqueness vs non-archived siblings (400 on conflict), `save_to_file()`. |
| `POST …/test_code_tool` | POST | `agent_policy_require_approval("Allow agent to run Python code on your machine? It may call your tools, with side effects.")` | §6.1. Transient; persists nothing. |
| `GET …/code_tools` | GET | `ALLOW_AGENT` | id, name, tool_function_name, descriptions, is_archived, created_at; archived sorted last. |
| `GET …/code_tools/{id}` | GET | `ALLOW_AGENT` | Full artifact; 404 if missing. |
| `PATCH …/code_tools/{id}` | PATCH | `ALLOW_AGENT` | Request model has **only** `name` and `description` fields, so functional edits are structurally impossible; unknown fields rejected by FastAPI/Pydantic. Error copy for docs/UI: "functional content is immutable — clone instead". |
| `POST …/code_tools/{id}/archive` | POST | `ALLOW_AGENT` | `{archived: bool}` (tool-server archive mirror). Non-destructive, reversible. |
| `DELETE …/code_tools/{id}` | DELETE | `DENY_AGENT` | `code_tool.delete()` (removes folder). Humans only; archive is the agent path. |
| `available_tools` | GET | existing | Gains the CODE group (§2). |

### 6.1 Test endpoint (transient — `test_v2_eval` pattern)

```python
class TestCodeToolRequest(BaseModel):
    tool_function_name: str; tool_description: str = "test"
    parameters_schema: dict[str, Any]; code: str
    timeout_seconds: int = 60; tool_allowlist: list[ToolId] = []
    params: dict[str, Any]                       # invocation arguments

class TestCodeToolResponse(BaseModel):
    result: str | None = None
    error: str | None = None; traceback: str | None = None
    not_trusted: bool = False                    # nothing executed; UI shows trust dialog + retries
    stdout: str = ""; stderr: str = ""           # 64 KB truncation + marker; UI display is P2
    tool_call_log: list[ToolCallLogEntry] = []
    duration_ms: int = 0
```

Flow: build transient `CodeTool(parent=project, name="test_run", ...)` — `ValidationError`/`ValueError` → 400 with the validator message (identical text to create failures). Untrusted → `{not_trusted: true}` (200). Validate `params` against `parameters_schema` (400 on mismatch). Then replicate the root-agent lifecycle (MCP tools require it): `generate_agent_run_id()` + `set_agent_run_id()`; construct `PythonCodeTool(code_tool, project, task=None, tool_call_recorder=log.append)`; `await tool.run(ToolCallContext(allow_saving=False), **params)`; `finally`: `MCPSessionManager.shared().cleanup_session(run_id)` + `clear_agent_run_id()`. User-code failures return 200 with `error`/`traceback` populated (a failing test is a result, not an HTTP error); 4xx/5xx are reserved for validation and infrastructure faults. Nothing persisted (`test_nothing_persisted` assertion, copied from the eval suite).

Single execution path, two presentations: `PythonCodeTool` exposes the raw child outcome (`ChildOutcome`: result/stdout/stderr/error/traceback/duration) via an internal invoke method; `run()` folds it into `ToolCallResult`, the test endpoint folds it into `TestCodeToolResponse`.

## 7. Error handling strategy

- **Agent runs**: everything from the child or bridge maps to `ToolCallResult(is_error=True)` — a code tool failure never crashes the run (functional spec §2.4 is the contract; `error_message` gets the short form, `output` the model-facing text with user-frame traceback). Only artifact-resolution failure raises (matches MCP/RAG dangling-ID behavior).
- **Inside user code**: typed exceptions (`ToolNotAllowed`, `ToolTimeout`, `ToolCallError` with `.tool/.message/.raw`) are catchable for retries/fallbacks. Uncaught → error result with the user's line visible.
- **API**: 400 validation, 404 missing, 200-with-error for user-code test failures.
- **Logging**: parent logs child crashes/timeouts at `warning` with the tool id (never echoes user code); stdout/stderr never logged in agent runs.

## 8. Testing strategy

pytest (+ `pytest-asyncio`), vitest for UI — repo standards; shaped after the code-evals suites.

1. **Datamodel** (`test_code_tool.py`): validation trio with `def run` AND `async def run` accepted; missing/nested `run` rejected; schema/allowlist validators (skill/unmanaged/self/dup); defaults; save/load round-trip; parent registration.
2. **ToolId/registry**: build/parse/`_check_tool_id`; `tool_from_id` resolution + missing-artifact error; `tool_from_id_and_project` equivalence with and without a task.
3. **Execution engine**: full matrix in the [component doc](components/execution_engine.md) §5 — sync/async entry, string pass-through (no parsing), `async_tools` concurrency, timeout/crash/depth/semaphore, spawn-lock identity with `run_scorer`.
4. **API** (`test_code_tool_api.py`): create + uniqueness conflict; PATCH accepts name/description only (functional fields structurally rejected); archive; delete; test endpoint — validation 400s, `not_trusted`, success with `tool_call_log`, error mapping, `test_nothing_persisted`, MCP-session lifecycle.
5. **Regression**: entire existing code-eval suite passes unchanged after the `sandbox/` extraction (incl. async-`score` tests and the perf harness).
6. **UI (vitest)**: `code_tool_helpers` codegen (typed params, optionals, import-helper idempotence, never-clobber rule); wizard step state through `pushState`; test-panel state machine incl. trust intercept — mirroring `code_eval_form.test.ts` style.

## 9. Risks / non-obvious constraints

- **One `_spawn_lock` across features** — the eval refactor is mandatory, not cosmetic (PyInstaller #7410).
- **Queue payloads are JSON-level types only**; the child JSON-roundtrips tool-call arguments before sending (clear in-frame error if not serializable).
- **Blocking `Queue.get` can't be cancelled in an executor thread** — the pump uses short-interval polling with deadline + child-liveness checks (component doc), never an unbounded get.
- **`asyncio.Semaphore` loop binding** — create lazily inside the running loop.
- **MCP calls need `agent_run_id`** — present in agent runs; the test endpoint replicates the root-agent lifecycle (§6.1).
- **Frozen builds**: child entry stays within `multiprocessing.spawn` bootstrap; `freeze_support()` untouched; verify on all three OS targets in the release checklist (same bar as code-evals).
- **Branch coordination**: base is `scosman/evals_v2`; the async-`score` fix lands there independently — `sandbox/entrypoint.py` subsumes its logic at extraction time, and its tests keep passing either way.
