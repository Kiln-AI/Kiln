---
status: complete
---

# Functional Spec: Code Tools

A new tool type for Kiln: **Code Tools** — user-authored Python stored as a project artifact, executed as a tool inside the agent harness, with full UI + API for creating and testing. Within its Python, a code tool can call other tools it has been explicitly granted access to.

Target repo: `Kiln-AI/kiln`, branched off `scosman/evals_v2` (reuses its code-eval machinery; assumes the **async-`score` fix** has landed on that branch — see decisions log). Scope: backend + API + UI only — no AI authoring ([project_overview.md](project_overview.md) has the locked decisions; §11 below logs the decisions added/revised during this spec's Q&A).

Everything here applies to the **desktop app** (`app/desktop` + `app/web_ui`) and the core library (`libs/core/kiln_ai`). There is no server-side execution path, ever (locked decision 4).

## 1. The Code Tool artifact

A project-level Kiln artifact (a `.kiln` file under the project, like `ExternalToolServer`, `RagConfig`, `Skill`).

### 1.1 Fields

**Kiln artifacts are mostly immutable, for eval consistency.** Functional content is frozen at create time; changing it means cloning into a new tool (new ID), so run configs and their eval results always refer to exactly the code they exercised. Only non-load-bearing metadata is editable.

| Field | Type | Mutable? | Rules |
|---|---|---|---|
| `name` | string | ✏️ editable | User-facing display name. Standard `FilenameString` rules. Required. |
| `description` | string | ✏️ editable | User-facing notes shown in the UI. Optional. **Not** shown to models. **P2** — cut it if it ends up unneeded or clutters the UI; the field earns its place only if the detail page wants it. |
| `is_archived` | bool | ✏️ editable | Default false. Archived tools are hidden from pickers but still resolve if referenced by an existing run config (matches `ExternalToolServer`). |
| `tool_function_name` | string | 🔒 immutable | The function name exposed to the model (and to other code tools). Snake_case identifier (`^[a-z][a-z0-9_]{0,63}$`, mirroring the UI `tool_name_validator`). Required. Unique among the project's non-archived code tools (enforced at the API layer). |
| `tool_description` | string | 🔒 immutable | Shown to agents as the tool description. Required, non-empty. |
| `parameters_schema` | JSON Schema | 🔒 immutable | The tool's parameters, per MCP/OpenAI function-calling standards. Root must be `type: "object"`; empty `properties` allowed (zero-argument tools). Validated with the existing `validate_schema_dict`. |
| `code` | string | 🔒 immutable | Inline Python source, stored in the `.kiln` JSON (code-evals precedent). Validation: §1.2. |
| `timeout_seconds` | int | 🔒 immutable | Wall-clock timeout for one invocation, **including** time spent in nested tool calls. Default **60**, min 1, **no max**. |
| `tool_allowlist` | list[ToolId] | 🔒 immutable | Explicit per-tool allowlist of tools this code tool may call. Default `[]`. §4. |

Plus the standard `KilnBaseModel` fields (`id`, `v`, `created_at`, `created_by`). The display-name/function-name and display-description/model-description splits follow the kiln-task-as-tool convention (`ExternalToolServer` fields vs its `properties`).

### 1.2 Save-time code validation ("compilation checks")

Runs on every construction/deserialization (Pydantic model validator — same trio as code-evals):

1. **Size cap**: UTF-8 encoded code ≤ 64 KB.
2. **Syntax**: `compile(code, "<code_tool>", "exec")`; `SyntaxError` fails the save with the error message.
3. **Entry-point check (AST)**: a module-level `run` function must exist — **either `def run` or `async def run`** (both are executable, §3.1).

Additional save-time validation: `parameters_schema` validity (root object); every allowlist entry is a valid `ToolId`; **skill tool IDs rejected** (`kiln_tool::skill::…` — adapter-resolved, not callable from code) and **unmanaged IDs rejected** (SDK-injected, unresolvable); no duplicate allowlist entries; no self-reference.

There is **no** save-time check that `run()`'s parameters match `parameters_schema` (optional fields, `**kwargs` catch-alls make it noisy). A mismatch surfaces at call time as a normal execution error; the live test panel is where authors catch it before saving.

### 1.3 Lifecycle

- **Create**: the only moment functional content is set. The creation flow includes live testing before save (§6).
- **Edit**: display `name`, `description`, `is_archived` only.
- **Clone**: the "edit the code" path — pre-fills a new-tool creation flow from an existing tool; saving produces a new artifact/ID (a new `tool_function_name` will be required if the source isn't archived, per the uniqueness rule).
- **Archive/unarchive**: soft hide from pickers; existing references keep working.
- **Delete**: hard removal (humans only, §7). A run config referencing a deleted tool fails at tool-resolution time with the standard "tool not found" error (existing behavior for MCP/RAG/task tools — no new referential-integrity machinery).

## 2. Agent-harness behavior

### 2.1 Identity and registration

- New `ToolId` format: **`kiln_tool::code::<code_tool_id>`** with build/parse helpers (RAG-tool pattern); new branch in `tool_from_id()` loading the artifact from the task's parent project.
- `toolcall_definition()` = `tool_function_name` / `tool_description` / `parameters_schema` (OpenAI-compatible). No snapshotting needed — the artifact is immutable.
- Attached to runs via `ToolsRunConfig.tools` like any tool; existing rule that function names are unique within one run config applies unchanged.

### 2.2 Execution semantics

One invocation = one **spawned subprocess** (the code-evals sandbox pattern):

- `multiprocessing` spawn context; the `__main__` stub-swap trick under `_spawn_lock` is kept (PyInstaller Linux concurrent-spawn bug #7410 + the swap window; both only span `p.start()`). The lock is **shared** with code-evals via an extracted helper.
- The child `exec()`s the code and calls `run(**args)` with the model-provided arguments (already schema-validated by the adapter before dispatch). If `run` is async, the child drives it with its own event loop (`asyncio.run`) — same shared helper that executes async `score` for code evals.
- stdout/stderr are captured in the child (also prevents None-stdout crashes in windowed PyInstaller builds). In agent runs they are **discarded** — never sent to the model, never stored on traces. (They surface only via the test API, §6.)
- **Wall-clock timeout** from `timeout_seconds` covers the entire invocation including nested tool calls. On timeout the child is killed and in-flight nested calls are cancelled parent-side (side effects of already-dispatched calls may have landed — documented, not prevented).
- **Concurrency**: no global execution lock (deliberate departure from code-evals). Executions run in parallel, bounded by a process-wide semaphore — default **8**, a library constant, counting **top-level invocations only**. Nested code-tool executions bypass the semaphore (counting them deadlocks the pool: parents hold slots while blocked on children). Worst case is 8 × nesting-depth processes.

### 2.3 Results returned to the model

`run()`'s return value becomes the tool output string: `str` passes through as-is; `dict`/`list`/`int`/`float`/`bool`/`None` are `json.dumps`-ed; anything not JSON-serializable is an invocation error. (This outbound convenience is deterministic — the author controls their own return type — unlike inbound parsing, which is why the two directions differ; see §3.3.)

### 2.4 Errors returned to the model

Code tool failures **never crash the agent run**. Everything maps to `ToolCallResult(is_error=True, ...)` so the model sees the error as tool output and can adapt (the MCP `isError` contract):

| Failure | Output the model sees |
|---|---|
| User code raises | Exception type + message + traceback trimmed to user-code frames (`<code_tool>` file). |
| Timeout | `Code tool '<name>' timed out after <N>s`. |
| Child crash (non-zero exit, no result) | `Code tool '<name>' crashed (exit code N)`. |
| Non-serializable return value | Targeted message naming the offending type. |
| Project not trusted (§5) | Error stating code tools are disabled until the project is trusted in Kiln. |
| Artifact missing/broken at resolution | Standard `tool_from_id` resolution error (this one **does** fail the run, matching MCP/RAG dangling-ID behavior). |

## 3. The in-Python authoring contract

### 3.1 Entry point — sync or async

```python
def run(...) -> str | dict | list | int | float | bool | None
async def run(...)                                   # equally supported
```

Module-level, called with keyword arguments matching `parameters_schema` properties (absent optional properties are simply not passed — authors provide Python defaults). For `async def run`, the wrapper owns the event loop — user code just `await`s and stays focused on the task:

```python
async def run(urls, concurrency=50):
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=10) as client:
        async def bounded(u):
            async with sem:
                return await fetch(client, u)
        return await asyncio.gather(*(bounded(u) for u in urls))
```

One documented consequence: code inside an async `run` must not call `asyncio.run()` itself (no nested event loops). Sync `run` bodies may freely use `asyncio.run(...)` for async sections.

### 3.2 Environment

- **Interpreter**: the Kiln app's own bundled Python; imports = stdlib + everything shipped in the Kiln bundle (`kiln_ai.*` included). No requirements/venv management (locked decision 5).
- **No language sandbox**: no import restrictions, no resource limits beyond the wall-clock timeout, unrestricted filesystem/network — it's the author's machine; the trust gate (§5) is the security model, exactly as for code-evals.
- **No direct secrets**: all external access goes through allowlisted tools (MCP owns auth). Locked decision 6.
- User code may spawn threads and use asyncio; the tool-calling API is safe from both (§3.3).

### 3.3 Calling other tools — `kiln.tools` / `kiln.async_tools`

Namespaced-proxy style (locked decision 7). A synthetic `kiln` module is importable inside the sandbox child only (no real top-level `kiln` package ships; importing it outside code-tool execution fails):

```python
from kiln import tools                     # sync code
from kiln import async_tools               # async code — the same API, awaitable

def run(job_ids: list[str]) -> dict:
    user = json.loads(tools.get_user(id=1234))          # attribute = tool function name
    ...

async def run(user_ids):
    results = await asyncio.gather(*(async_tools.get_user(id=u) for u in user_ids))
```

Contract (identical for both modules; `async_tools.<name>` is the awaitable mirror of `tools.<name>` — truly concurrent under `gather`):

- `tools.<function_name>(**kwargs)` — blocks until the tool returns. Attribute access always succeeds; **resolution against the allowlist happens at call time**. (Bare `tools.x()` inside async code works but blocks the event loop — use `async_tools` there; documented.)
- kwargs must match the target tool's JSON Schema; validated before dispatch (invalid → `ToolCallError`).
- **Returns are always `str`** — byte-for-byte what the model would have seen from that tool. No auto-parsing, no type instability; tools that return JSON are parsed by the author (`json.loads`, one line — shown in generated placeholder code). Failures come via typed exceptions, never a differently-shaped return.
- `tools.list_tools() -> list[dict]` — the allowlisted tools as `{name, description, parameters_schema}`, for introspective code. (Reserved name; the method wins over a same-named allowlisted tool — documented.)
- **Typed exceptions** (importable from `kiln.tools`):
  - `ToolNotAllowed` — name doesn't resolve to any allowlisted tool; message lists available names.
  - `ToolTimeout` — the nested tool itself reported a timeout (identifiable cases: nested code tools, asyncio timeouts; other tools' timeout errors arrive as `ToolCallError` with the raw message).
  - `ToolCallError` — everything else: tool returned an error, kwargs failed schema validation, allowlisted tool failed to resolve (e.g. its MCP server was deleted), ambiguous name (§4.2). Fields: `.tool`, `.message`, `.raw` (raw output string when there is one).
- **Concurrency-safe**: calls may be issued from multiple threads or gathered coroutines simultaneously; the harness executes them concurrently. **No batch/parallelism helper API** — authors write their own with stdlib; a parallel-with-retries example ships in docs (locked decision 7).

### 3.4 Nested-call semantics

- Nested tool calls execute in the **parent (app) process**, inside the calling agent run's async context — agent-run contextvars propagate, so nested MCP calls reuse the run's sessions.
- Sub-agent (kiln-task) tools behave exactly as if the agent called them: run saving honors the calling context's `allow_saving`; traces link via existing mechanisms.
- **Code tools are just tools** — they can call other code tools, with no special capability constraints. Each nested code tool gets its own subprocess, timeout, and allowlist. A **max nesting depth of 10** exists purely as a runaway guard (save-time cycle detection is impossible: A→B→A); hitting it raises `ToolCallError` ("max code tool depth exceeded — check for a cycle").

## 4. Allowlist semantics

### 4.1 What can be allowlisted

Any resolvable `ToolId`: MCP tools (remote/local, individually — never per-server, locked decision 2), RAG tools, Kiln-task tools, built-in tools, other code tools. **Not** skills, **not** unmanaged tools (§1.2).

### 4.2 Name resolution

- `tools.<name>` matches `<name>` against the **function names** of allowlisted tools, derivable without network calls (MCP tool name is embedded in the ToolId; RAG/task/code names come from local artifacts).
- Name not found → `ToolNotAllowed`. Two allowlisted tools sharing a function name (e.g. two MCP servers both exposing `search`) → `ToolCallError` "ambiguous" at call time; the UI warns about duplicates in the picker but save isn't blocked (external names can drift post-save regardless).
- New tools appearing on an allowlisted MCP *server* are **not** callable — the allowlist pins exact tools; capability never silently leaks (locked decision 2).

## 5. Trust gate — deliberately unspecified (parallel work in flight)

There is in-flight work on the project-trust experience, so this spec **does not define** the trust mechanism, persistence, revocation, dialog UX, endpoint shapes, or whether one grant covers both code-evals and code tools. Only these invariants hold regardless of what that work produces:

1. **Code never executes in an untrusted project.** Agent runs get the §2.4 error tool-result; the test endpoint gets a structured not-trusted response the UI can react to.
2. **The grant lives desktop-side only** — `kiln_server` never grants trust; this is part of the desktop-only enforcement.
3. **Interim wiring during development** (phases 1–4): code tools call the existing code-eval trust check (`is_code_eval_trusted`) and the test flow reuses the existing eval trust endpoints/dialog pattern as a stopgap — zero new footprint on the trust module.
4. **Ship blocker**: the final implementation phase replaces the stopgap with whatever the trust work lands. Code Tools does not ship without it.

## 6. Testing a code tool (live test)

Live execution of **editor state** (not-yet-saved content) against **real allowlisted tools**, behind the trust gate, with a side-effects warning; no mock mode (locked decisions 9–10). Used from the creation flow's test panel and from the detail page of a saved tool.

Test endpoint contract (transient pattern — `test_v2_eval` precedent: build unsaved model → validation runs implicitly → execute → persist nothing):

**Request**: the functional field set (`tool_function_name`, `parameters_schema`, `code`, `timeout_seconds`, `tool_allowlist`) + `params: dict` (invocation arguments, validated against `parameters_schema` before execution).

**Response**:

| Field | Contents |
|---|---|
| `result` | The serialized output string (what the model would see); null on failure. |
| `error` / `traceback` | Failure message + user-frame traceback; null on success. |
| `not_trusted` | True when the project isn't trusted (nothing executed). |
| `stdout` / `stderr` | Captured from the child, truncated to 64 KB each with marker. In the API from v1; **UI display is P2.** |
| `tool_call_log` | Nested calls made: `{tool_name, arguments, output_preview, is_error, duration_ms}` — recorded parent-side. |
| `duration_ms` | Wall-clock execution time. |

Validation failures (syntax error, bad schema, bad allowlist entry) → 400 with the validator's message — identical text to save failures. User-code failures → 200 with `error`/`traceback` populated (a failing test is a *result*, not an HTTP error).

## 7. API surface (desktop `studio_server`)

Agent access uses the existing `x-agent-policy` machinery (`ALLOW_AGENT` / `DENY_AGENT` / `agent_policy_require_approval("…")` from `kiln_server/utils/agent_checks/policy.py`). Design principle: the API is the contract, nothing assumes a human is driving — agents may do everything a human can, with **approval gates instead of denial** on the risky calls (a separate future project adds containers for safer unattended agent usage; until then, per-call approval is the mechanism).

| Endpoint | Method | Agent policy | Notes |
|---|---|---|---|
| Create code tool | POST | **approval** — "Allow agent to create and save a code tool (Python that runs on your machine)?" | Full functional field set + metadata; `tool_function_name` uniqueness enforced (400 on conflict). |
| Test code tool | POST | **approval** — "Allow agent to run Python code on your machine (may call your tools, with side effects)?" | §6. Transient; persists nothing. |
| List code tools | GET | allow | id, names, descriptions, archived flag, created_at. |
| Get code tool | GET | allow | Full artifact. |
| Edit metadata | PATCH | allow | **Only** `name`, `description` — non-load-bearing metadata by construction; functional fields rejected with a clear "immutable — clone instead" error. |
| Archive/unarchive | POST | allow | Non-destructive, reversible. |
| Delete | DELETE | deny | Destructive; humans only. Archive is the agent-safe path. |
| Trust endpoints | — | — | Unspecified (§5); stopgap = existing eval endpoints. |
| `available_tools` | GET | allow (existing) | Gains a "Code Tools" tool-set group (non-archived only) so run-config pickers and the allowlist picker work with zero extra plumbing. |

**Code-eval endpoints are out of scope** — do not change their agent policies (or anything else about them) in this project.

**Security-string backstop**: the approval-prompt strings above (and any other security-related copy, e.g. trust/side-effects warnings) are drafts pending human review. In code, each must carry a `# TODO` comment stating that removing/finalizing it requires human sign-off. This is a real backstop, not documentation: CI blocks `TODO` from merging to main, so the strings physically cannot ship unreviewed.

After create/archive, the UI calls `uncache_available_tools()` (existing convention) so run-page dropdowns refresh.

## 8. UI scope (functional level — details in [ui_design.md](ui_design.md))

1. **Add Tools flow**: a "Code Tool" card in the Custom Tools section of `tools/[project_id]/add_tools/`.
2. **Creation flow — two screens**, per the authoring-UX decision:
   - **Screen 1 — Define** (mix of "new task" UI and tool UI, heavy reuse): display name, tool function name, model-facing description, and the parameter signature via the existing JSON-schema builder (the "new task" input-schema experience). No output schema — MCP tool outputs are untyped in practice.
   - **Screen 2 — Code & Test** (the code-eval page shape): code editor on the left, live test panel on the right. The editor is pre-filled with a **generated placeholder `run()` whose parameters match the schema, fully typed**, including a commented example tool call (and `json.loads` where relevant). Allowlist picker and timeout live on this screen (advanced section).
3. **Detail page** for a saved tool: read-only code + metadata edit (display name/description) + test panel + **Clone** (the path to changing code) + archive.
4. **Tools index**: code tools listed with links to detail pages.
5. **Run-config tools dropdown**: Code Tools group appears automatically via `available_tools`.

## 9. Edge cases (consolidated)

- **Zero-argument tool**: allowed; empty test form with just Run.
- **`run(**args)` signature mismatch with schema**: child raises `TypeError` → error result with traceback; caught in the test panel during authoring.
- **Author prints megabytes**: captured in-memory child-side, truncated at 64 KB per stream in the test response.
- **Nested tool output is huge**: passed through untouched (code tools exist precisely to filter/compact such outputs).
- **Cycle A→B→A**: halts at depth 10 with `ToolCallError`; self-reference blocked at save.
- **Timeout with nested calls in flight**: child killed, parent-side dispatch cancelled; dispatched side effects may have landed (covered by the test panel's side-effects warning).
- **App quits mid-execution**: children are daemons — they die with the app.
- **Concurrent invocations of one code tool**: independent subprocesses; fine.
- **Allowlisted MCP server deleted after save**: call-time `ToolCallError`; the code tool itself still loads.
- **Archived code tool still referenced by a run config**: resolves and executes (archive only hides from pickers).
- **Windows/macOS/Linux + frozen builds**: explicit spawn context, `freeze_support()` untouched, stub-swap within multiprocessing's bootstrap — same guarantees and perf harness as code-evals.

## 10. Out of scope

Tool-writing agent / AI authoring; server-side execution (never); mock/simulated tool backends; dependency management beyond stdlib + Kiln bundle; secrets storage; companion Python test files; batch/parallelism helper API (docs example instead); typing stubs for editor autocomplete (later enhancement); **containers for safer unattended agent usage** (tracked separately — until then, approval gates cover agent usage); trust-gate design (in-flight elsewhere, §5).

## 11. Decisions log (Q&A with scosman, 2026-07-05)

1. Entry point named `run`; **both `def run` and `async def run` supported** — the wrapper owns the event loop. Shared sandbox helper also powers code-evals' async `score` (the evals_v2 fix, handed off separately).
2. In-sandbox API: `from kiln import tools` (sync) + `from kiln import async_tools` (awaitable mirror; `tools.async.…` impossible — `async` is a reserved keyword). `list_tools()` included.
3. **Nested-call returns are always `str`** — no auto-parsing (type stability; fidelity to what the model sees; MCP is native strings; `json.loads` is one line). Revises overview decision 7's "plain Python (dict/list/str)" wording. Outbound `json.dumps` of `run()`'s dict/list return kept (deterministic, author-controlled).
4. Composition unrestricted — code tools are just tools. Depth cap 10 as runaway/cycle guard only. Semaphore (8) counts top-level invocations only (nested bypass to avoid pool deadlock). Timeout = whole-invocation wall clock including nested calls.
5. stdout/stderr: discarded in agent runs; in the test API response from v1; test-pane display P2.
6. **Immutability**: functional content frozen at create; clone to change; only display name/description/archived editable. Two-screen authoring flow (define → code+test) with typed placeholder codegen from the schema; no output schema.
7. Agent access: reads/metadata-edit/archive allowed; create/test **approval-gated** (not denied); delete denied. Containers for safer agent usage tracked separately. Code-eval endpoint policies: out of scope, don't touch. Security-related strings ship behind `# TODO` comments requiring human sign-off (CI blocks TODO on main — a real backstop).
8. Trust gate: **deliberately unspecified** — parallel in-flight work; invariants + interim stopgap wiring only; final phase of the implementation plan; ship blocker.
9. User-facing `description` field is P2 — cut if unneeded or if it clutters the UI.
