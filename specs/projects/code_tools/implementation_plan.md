---
status: complete
---

# Implementation Plan: Code Tools

Build happens in `Kiln-AI/kiln` on a feature branch **off `scosman/evals_v2`** (this spec folder lives in the O3 planning repo — copy or reference it when dispatching coding agents). Planning note: keep a local clone of kiln checked out at `scosman/evals_v2` while implementing — every file path and reuse claim in these specs was verified against that branch (head `76f56b8` at spec time). The separate **async-`score` eval fix** lands on that branch independently; phase 1 absorbs it in either order.

Each phase is independently reviewable and leaves the branch green (full existing test suite passes — notably the complete code-evals suite from phase 1 onward, unchanged).

## Phases

- [x] **Phase 1: Library foundations** — `kiln_ai/sandbox/` package: `spawn.py` (shared `_spawn_lock` + stub-swap helper) and `entrypoint.py` (`call_entrypoint`, sync/async); mechanical refactor of `adapters/eval/sandbox_worker.py` to delegate to both (behavior-identical, eval suite green); `datamodel/code_tool.py` + `Project.parent_of` + exports; `tool_id.py` prefix/helpers; registry refactor (`tool_from_id_and_project`) + `kiln_tool::code::` branch. Tests: architecture §8.1–2 + full eval regression.
- [x] **Phase 2: Execution engine** — `sandbox/worker.py`, `sandbox/tools_api.py` (`kiln.tools` / `kiln.async_tools`, typed exceptions, bridge), `tools/code_tool.py` (`PythonCodeTool`: trust stopgap behind interim-trust `# TODO`, depth cap 10, top-level-only semaphore, message pump, nested dispatch, error mapping). Tests: [components/execution_engine.md](components/execution_engine.md) §5, including the semaphore deadlock-regression test.
- [x] **Phase 3: Desktop API** — `code_tool_api.py` (create, list, get, metadata-only PATCH, archive, delete, transient test endpoint with agent-run-id lifecycle), agent policies incl. approval gates (security strings behind sign-off `# TODO`s), `available_tools` CODE group, wire into `desktop_server.py`, regenerate `api_schema.d.ts`. Tests: architecture §8.4 incl. `test_nothing_persisted`.
- [x] **Phase 4: Web UI** — add-tools cards (suggested — removing Control GitHub — + custom); two-step create wizard (`pushState` steps: Define with `SchemaSection`, Code & Test with typed-placeholder codegen, import-helper, `tools_selector` allowlist, test panel, trust-dialog stopgap); detail page (readonly code, metadata edit, test panel, clone, archive); tools-index rows (Type "Code Tool", Status Ready/Archived); `code_tool_helpers.ts` + vitest per architecture §8.6; per [ui_design.md](ui_design.md).
- [ ] **Phase 5: Polish + docs** — examples-dialog content (parallel-with-retries via threads, `async_tools` fan-out, `json.loads` filtering) and matching docs; cross-OS spawn sanity (macOS/Windows/Linux + frozen-build checklist item); PostHog events; empty states. P2 items (stdout/stderr display, code copy button, user-facing description field) only if trivial — otherwise leave tracked.
- [ ] **Phase 6: Trust integration — UNDEFINED, ship blocker** — deliberately unplanned (functional spec §5): parallel in-flight work owns the trust design. When it lands: replace the two stopgap call sites (`PythonCodeTool.run`, test endpoint) and the UI's borrowed eval trust dialog with the real mechanism; finalize all security-related strings (human sign-off removes their `# TODO`s). CI's TODO-block guarantees phases 2–4's stopgap cannot reach main — **Code Tools does not ship until this phase is resolved.**
