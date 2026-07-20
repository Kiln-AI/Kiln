---
status: complete
---

# Refactor: shared sibling-code-file storage helper

Behavior-preserving refactor of the just-shipped "code as files" persistence
(Phases 1–4). Today the read-on-load / write-on-save logic is DUPLICATED between
`CodeTool` (`tool.py`) and `CodeEvalProperties` (`scorer.py`), and the code-eval
eager-parse-on-load is smeared into the generic
`EvalConfig.dispatch_properties_parsing`. This refactor centralizes the shared
mechanism and makes the code-eval type-gate explicit. No on-disk format, load/
save semantics, error-message clarity, API/model-dump behavior, or JSON schema
changes.

## Steps

1. **New shared module** `libs/core/kiln_ai/datamodel/code_file_storage.py`
   (stdlib-only: `pathlib`, `typing`). Two module-level functions both models
   call from thin validators/serializers. This is the ONE audited place for path
   containment: a fixed, bare filename (passed by the caller) joined to the
   folder from context — no traversal, no absolute paths, no import/exec.
   - `read_code_from_sibling_file(data, ctx, *, filename, kiln_filename, model_label)`
     — the before-validator body. When `ctx["loading_from_file"]` is set, `data`
     is a dict, and `"code" not in data`, read `<source_dir>/<filename>` into a
     copy of `data` as `data["code"]`. Raise a clear `ValueError` if `source_dir`
     is missing (`"Cannot load {model_label}: source_dir missing from load
     context"`) or the file is unreadable (`"{kiln_filename} at {src} is missing
     its {filename} (expected at {code_path}): {e}"`) — byte-identical to today's
     messages. Keep the lenient `"code" not in data` guard. Copy-on-write (never
     mutate the caller's input dict).
   - `write_code_to_sibling_file(data, ctx, *, filename, code)` — the serializer
     body. When `ctx` has `save_attachments` + `dest_path`, validate `dest_path`
     is an existing directory (else clear `ValueError`, message unchanged), write
     `code` verbatim (UTF-8) to `<dest_path>/<filename>`, and return a copy of
     `data` without `code`; otherwise return `data` unchanged and write nothing.
   - A private `_require_bare_filename` guard documents/enforces containment
     (callers only ever pass module constants, so it never triggers in practice).

2. **Rewire `CodeTool` and `CodeEvalProperties`** to call the helpers from their
   `_read_code_file` / `_serialize`. Each keeps its `*_CODE_FILENAME` constant.
   `CodeEvalProperties.__get_pydantic_json_schema__` STAYS (it is a FastAPI
   `response_model` member — schema stability). Do NOT add that override to
   `CodeTool` (would change its schema).

3. **Explicit code_eval type-gate (eval path).**
   (a) Lift the code-eval block out of the generic
   `EvalConfig.dispatch_properties_parsing` into a module-level, clearly-named
   `_eager_parse_code_eval_on_load(data, ctx)`, keeping its explicit
   `props.get("type") == V2EvalType.code_eval.value` gate. The generic/legacy
   dispatch behavior is byte-identical.
   (b) Add a defensive `type == code_eval` assertion in
   `CodeEvalProperties._read_code_file` (raises only for a present, mismatched
   `type`; None / `code_eval` / the enum all pass — valid-input behavior
   unchanged).

## Behavior-preservation checkpoints

- On-disk `.kiln` still omits `code`; sibling `.py` written verbatim; API/plain
  dumps still include `code`; save is idempotent.
- Error messages (missing `source_dir`, unreadable sibling file, non-directory
  `dest_path`) unchanged.
- `CodeEvalProperties` serialization-mode JSON schema == validation-mode
  (`__get_pydantic_json_schema__` retained); no `-Input`/`-Output` split.
- Missing/corrupted `scorer.py` still surfaces the direct error on load (eager
  parse), not the generic "V2 config requires typed properties".

## Tests

- New `test_code_file_storage.py` unit-tests the helper directly: load injects
  code; missing `source_dir` errors; unreadable file errors; lenient skip when
  `"code"` already present / not loading; save writes file + pops code under save
  context; no-op (no write, code kept) without context; non-directory
  `dest_path` errors; COW (input dict not mutated).
- Keep existing model tests (`test_code_tool.py`, `test_eval_model.py`) green —
  they already cover the wired behavior end-to-end.

## Checks

`uv run ./checks.sh --agent-mode` until clean (noting pre-existing out-of-scope
failures). Targeted suites: `test_code_tool.py`, `test_code_tool_api.py`,
`test_eval_model.py`, plus eval-adapter + sandbox suites as regression.
