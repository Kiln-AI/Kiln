---
status: complete
---

# Implementation Plan: Code as Files

Phased build order for [architecture.md](architecture.md). Each phase is independently reviewable and leaves the suite green.

## Phases

- [x] **Phase 1 — Code tool file storage.** Base-model load-context change (`source_dir`); `CodeTool` before-validator (read `tool.py`) + wrap serializer (write `tool.py`, omit `code` from the `.kiln`, keep it in API dumps). Round-trip + missing-file + clone/delete + API-dump tests. (`basemodel.py`, `datamodel/code_tool.py`, `test_code_tool.py`.)

- [x] **Phase 2 — Code judge file storage.** Same treatment for `CodeEvalProperties` → `scorer.py`, including the nested-in-`EvalConfig.properties` path. **Verify context propagation to discriminated-union members first**, then build. Nested round-trip tests. (`datamodel/eval.py`, `test_eval.py`.)

- [x] **Phase 3 — The `kiln` test shim.** Extract the shared `kiln.tools` surface from `sandbox/tools_api.py` (behavior-preserving; sandbox suite unchanged); new `tool_testing/` pytest plugin + fake bridge + `kiln_tools` fixture; `pytest11` entry point. Shim tests incl. an end-to-end `tool.py`-imports-and-calls-`tools.x()` case. (`sandbox/tools_api.py`, `tool_testing/`, `libs/core/pyproject.toml`.)

- [ ] **Phase 4 — Wiring, fixtures, docs, regression.** Confirm the API/UI need no data-flow change (code still in responses); regenerate any inline-`code`-in-JSON fixtures/tests; export/zip + git-sync round-trip test for the sibling files; docs "Testing your tool / judge" sections; optional P2 detail-page snippet. Full `code_tools` + code-eval + sandbox suites green.
