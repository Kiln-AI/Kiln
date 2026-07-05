---
status: complete
---

# Code Tools — Project Overview

Add a new tool type to Kiln: **Code Tools** — user-authored Python that runs as a tool in the agent harness, stored in the Kiln project like other artifacts, with full UI + API for creating, editing, and testing them. Within its Python, a code tool can call the other tools it has been granted access to.

**Target repo:** `Kiln-AI/kiln` (library `libs/core/kiln_ai`, desktop server `app/desktop`/`studio_server`, web UI `app/web_ui`). **Branch off `scosman/evals_v2`** (merging shortly) — this project reuses its code-eval machinery wholesale. This is the backend + API + UI project only.

Reference research (in the O3 planning repo): [evals & code-evals](../../../research/kiln_tech/evals_and_code_evals.md) (the reuse target: validation, sandbox worker, test endpoint, editor/test-panel components), [tools & agent harness](../../../research/kiln_tech/tools_and_agents.md) (KilnToolInterface, tool_from_id registry, ToolId scheme, contextvar-propagated nested tool calls), [datamodel](../../../research/kiln_tech/datamodel.md) (artifact patterns, additive model types), [UI patterns](../../../research/kiln_tech/ui.md) (add_tools flow, schema builder, RAG test-panel analog).

## Why (one paragraph)

O3's translation-layer thesis: agents fail on messy interfaces — N+1 tool loops, context floods, missing batch APIs. Code tools are the durable artifact that fixes this in code instead of LLM loops (batch wrappers, context-engineering endpoints, result filters). They plug into the harness like any other tool. Humans author them via this project's UI; later projects (tool-writing agent — out of scope here) author them via this project's API.

## Decisions (locked, scosman 2026-07-04)

1. **Parameters are JSON Schema, per MCP standards**, stored in the datamodel. Manual authoring uses the existing schema-builder UI (same experience as new-task inputs/outputs). No AI inference of schemas — out of scope.
2. **Tool access is an explicit per-tool allowlist** (list of `ToolId`s in the datamodel). Not per-server: servers change, and new tools must not silently leak into a code tool's capabilities.
3. **Execution reuses the evals_v2 sandbox pattern**: `multiprocessing` spawn worker, wall-clock timeout, stdout/stderr/traceback capture, and the **same project trust gate** (grant/check/revoke + warning dialog).
   - **Timeout configurable in the datamodel.** Default 60s, no max.
   - **Concurrency**: keep `_spawn_lock` (required: PyInstaller Linux concurrent-spawn bug #7410 + the `__main__` stub-swap window; both only cover `p.start()`, sub-ms each). Do **not** copy the global `_code_eval_execution_lock`; replace with a bounded semaphore so tools run in parallel inside agent loops.
4. **Desktop-only, forever.** The server can't call other (client-side) tools, and server-side execution of user Python is a major security issue. No server execution path in this design.
5. **Dependencies: stdlib + the bundled Kiln helper library only** (same as code-evals). No requirements/venv management.
6. **No direct secret storage for code tools.** All external access goes through the allowlisted tools (MCP owns auth). A code tool never holds an API key.
7. **In-Python tool-calling API: namespaced proxy style — locked.** The vibe (exact module path up to the spec):
   ```python
   from kiln import tools

   def run(job_ids: list[str]) -> dict:
       user = tools.get_user(id=1234)  # attribute = tool name, resolved against the allowlist at call time
   ```
   - kwargs match the tool's JSON Schema; results are plain Python (dict/list/str).
   - Typed exceptions: `ToolNotAllowed`, `ToolTimeout`, `ToolCallError` (`.tool`, `.message`, `.raw`).
   - Sync facade in user code; the worker bridges to the async harness (`tool_from_id().run()`; agent-run contextvars propagate so nested MCP sessions work).
   - **No batch/parallelism helper API.** Tool calls must be **safe to invoke concurrently** (threads / gathered coroutines under the sync facade) so authors can write their own parallelism with stdlib; ship a parallel-with-retries *example* in the accompanying skill/docs instead of API surface.
   - Later enhancement (not v1): typing stubs generated from allowlisted schemas for editor autocomplete.
8. **Code stored inline in the `.kiln` JSON** (code-evals precedent: self-contained, diffable, same validation path).
9. **Test panel = live execution** against real allowlisted tools, behind the trust gate with a side-effects warning (the RAG "Test Search Tool" pattern). No mock mode in v1.
10. **No companion Python test file** in v1.
11. **Tool-writing agent is out of scope.** Keep this clean and small: backend + API + UI. (Kiln Assistant producing these via API calls is a later, separate project — but see Design Principles: the API is the contract.)

## Design principles

- **Reuse over rebuild** (from evals_v2): inline-code validation trio (size cap + `compile()` + AST entry-point check), subprocess worker, transient test-endpoint pattern (`test_v2_eval`-style: build unsaved config, execute, persist nothing), CodeMirror editor component, test-run pane, trust dialog.
- **API is the contract; the UI is a client of it.** No agent work here, but nothing in the API design should assume a human is driving.
- **Datamodel is additive**: new project-child artifact + new `ToolId` prefix (e.g. `kiln_tool::code::<id>`) + one new branch in `tool_from_id`, implementing `KilnToolInterface`. Zero migration.

## Datamodel sketch (for the spec to detail)

Project-child artifact with roughly: `name`, `description` (shown to agents), tool/function name, `parameters_schema` (JSON Schema), `code` (Python, inline), `timeout_seconds` (default 60, no max), `tool_allowlist: list[ToolId]`. Save-time validation: the code-evals trio, plus schema validity.

## UI scope

- New Tool flow: "Code Tool" card in `tools/[project_id]/add_tools/`.
- Create/edit page: name/description form, schema builder (existing component), CodeMirror editor, timeout field, tool-allowlist picker.
- Test panel: input form generated from the parameter schema → run → result/error/stdout display (live execution per decision 9).
- Trust dialog flow (reuse from code-evals).

## Revisions (2026-07-05, spec Q&A with scosman)

Logged here so this doc and the functional spec don't disagree; full log in [functional_spec.md](functional_spec.md) §11.

- **Decision 3 (trust gate)**: reuse deferred — parallel in-flight work on project trust; the spec defines invariants only, wires a stopgap during development, and makes trust integration the final (ship-blocking) implementation phase.
- **Decision 7 (in-python API)**: results are **always `str`** (not "plain Python (dict/list/str)") — no auto-parsing; authors `json.loads` when they know the tool returns JSON. Entry point supports **`async def run`** in addition to sync (the wrapper owns the event loop); async mirror `from kiln import async_tools` added alongside the sync facade; `tools.list_tools()` added.
- **New: immutability** — functional content (function name, model description, schema, code, timeout, allowlist) is frozen at create; clone to change; only display name/description/archived are editable. For eval consistency.
- **New: agent access** — create/test endpoints are approval-gated (`agent_policy_require_approval`), not denied; delete denied; the rest allowed.

## Out of scope

- Tool-writing agent / any AI authoring (later project, uses this API).
- Server-side execution (never, per decision 4).
- Mock/simulated tool backends (synthetic-tools project).
- Dependency management beyond stdlib + Kiln bundle.
- Secrets storage for tools.
- Companion Python test files.
- Batch/parallelism helper API (skill example instead, per decision 7).
