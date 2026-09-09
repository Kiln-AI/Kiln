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
- [x] **Phase 5: Polish + docs** — examples-dialog content (parallel-with-retries via threads, `async_tools` fan-out, `json.loads` filtering) and matching docs; cross-OS spawn sanity (macOS/Windows/Linux + frozen-build checklist item); PostHog events; empty states. P2 items (stdout/stderr display, code copy button, user-facing description field) only if trivial — otherwise leave tracked.
- [x] **Phase 6: Trust integration** — two complementary trust layers: (1) session-scoped code-execution trust on create/test/run endpoints, with a shared `CodeTrustDialog` component for the UI; (2) import-time project trust gate via a `trusted` query/body param on `POST /api/import_project` and `POST /api/git_sync/save_config`, with a full interstitial trust page in the import wizard (both local-file and git-sync flows). Security-related strings require human sign-off before their `# TODO`s are removed. See [phase_6.md](phase_plans/phase_6.md).
