---
status: complete
---

# Phase 4: Wiring, fixtures, docs, regression

## Overview

Phases 1–3 moved code-tool / code-judge Python out of the `.kiln` JSON into
sibling `tool.py` / `scorer.py` files and shipped the `kiln` test shim. Phase 4
is the closing phase: confirm nothing downstream (API responses, web UI) needs a
data-flow change, prove the sibling files travel through Kiln's export/copy
paths, and document the testing workflow the whole project exists to enable. It
is mostly verification plus one new test module and docs — no production
datamodel change is expected.

## Steps

1. **Confirm API/UI data flow is unchanged (verification, item 1).**
   - Code tools: `code_tool_api.py` returns dedicated response models
     (`CodeToolResponse`, `CodeToolCreateResponse`) built from the in-memory
     `ct.code` (populated from `tool.py` at load). No endpoint uses
     `response_model=CodeTool`. Web `code_tools/[code_tool_id]/+page.svelte`
     reads `code_tool.code` from that response. No change needed.
   - Code judges: `EvalConfig` is a FastAPI `response_model`; Phase 2's
     `__get_pydantic_json_schema__` override keeps `code` typed in the
     serialization schema, and a context-less API dump keeps `code`. Web
     `eval_config_builder.svelte` reads/writes `code_eval_code`. No change
     needed.
   - Deliverable: documented confirmation, no code edit. (If a real break were
     found it would be fixed minimally — none was.)

2. **Regenerate inline-`code`-in-JSON fixtures (item 2).**
   - Search core + app/desktop + web_ui for checked-in `.kiln` files and for
     tests that construct-save-then-assert JSON `code`. Result: zero `.kiln`
     files are checked in; the only save/load-and-assert tests are the Phase 1–2
     datamodel tests, already on the file-based layout. No fixtures to
     regenerate. The lenient loader is untouched.
   - Deliverable: documented search + confirmation, no code edit.

3. **Export/zip + git-sync round-trip test (item 3).**
   - The export/zip path is `cli/commands/package_project.py`
     (`package_project` / `package_project_for_training` →
     `export_evals`/`shutil.copytree` → `create_zip`). It exports evals (which
     carry code-judge `eval_config` folders) but has **no code-tool export
     path** (it never copies `code_tools`). (A code tool *can* be referenced from
     a run config's tool list via `CODE_TOOL_ID_PREFIX`, but `classify_tool_id`
     has no branch for it, so it classifies as "unknown" and `validate_tools`
     aborts packaging — a pre-existing packager limitation, out of scope here.)
   - Add tests in `cli/commands/test_package_project.py`:
     - **Code judge through the real export/zip path**: build
       `Task → Eval → EvalConfig(v2, CodeEvalProperties)` (writes `scorer.py`),
       run `package_project_for_training` with that eval id, assert `scorer.py`
       is in the zip and the reloaded eval config's `.code` is intact.
     - **Code tool through a filesystem-copy round-trip**: because
       `package_project` has no code-tool export path, copy the code-tool folder
       (`code_tool.kiln` + `tool.py`) to a new location (mirroring what
       git-sync / any folder copy does) and assert the reloaded tool's `.code`
       is intact. Documented in the test why the filesystem-copy path is used
       for tools.

4. **Docs — "Testing your tool" and "Testing your judge" (item 4).**
   - `docs/code_tools_guide.md` is the sole in-repo authoring-doc home for this
     feature family (no code-eval guide file exists). Add two sections there,
     matching the guide's format/style:
     - **Testing your tool**: write `test_tool.py` beside `tool.py`,
       `import tool`, use the `kiln_tools` fixture (`.set`, `.set_error`,
       `.calls`), run `pytest`. Cover the §7 caveat: one tool folder per pytest
       run to avoid `tool` module-name collisions (or `--import-mode=importlib`).
     - **Testing your judge**: write `test_scorer.py` beside `scorer.py`,
       `from scorer import score`, call `score(**inputs)` directly (no shim
       needed), using the real dynamic `score()` contract (only declared params
       passed; returns a dict keyed by output-score json keys).

5. **Optional P2 detail-page snippet (item 5).**
   - SKIP. Adding UI is out of proportion for a P2 static snippet given the web
     toolchain (node_modules) is not installed here and any UI change needs human
     sign-off. Noted as deferred.

6. **Regression (item 6).** Run and report counts for: code_tools datamodel +
   api, code-eval datamodel + eval adapter, sandbox suite, new tool_testing
   tests, and the new package_project round-trip tests. Confirm any failure is a
   documented pre-existing out-of-scope issue.

## Tests

- `test_code_judge_scorer_py_survives_training_export` — code judge's `scorer.py`
  travels through `package_project_for_training` (export + zip + reload); `.code`
  intact, `scorer.py` present in the zip.
- `test_code_tool_tool_py_survives_folder_copy` — code tool folder copied to a
  new location reloads with `.code` intact (the git-sync / folder-copy path;
  package_project has no code-tool export).
- Docs sections are prose (no automated test); verified by rendering/reading.
