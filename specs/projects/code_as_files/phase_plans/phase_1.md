---
status: complete
---

# Phase 1: Code tool file storage

## Overview

Move the user-authored Python of a `CodeTool` out of `code_tool.kiln` JSON and into a
fixed-name sibling file `tool.py` in the artifact folder. The in-memory `code: str` field
is unchanged — it is read from `tool.py` on load (before validators run) and written to
`tool.py` on disk-save, with `code` omitted from the `.kiln` JSON but kept in normal/API
model dumps.

This phase covers code tools only (code judges are Phase 2). The execution engine and the
sandbox are untouched. Nothing adds the artifact folder to `sys.path` or imports the sibling
file — this is storage only.

## Steps

1. **`datamodel/basemodel.py` — load context (`source_dir`).**
   In `KilnBaseModel.load_from_file` (line ~434), change the load-time validation context
   from `context={"loading_from_file": True}` to
   `context={"loading_from_file": True, "source_dir": path.parent}`.
   This is symmetric with the save side, which already passes `dest_path=path.parent`
   (line ~500). Other models ignore the new `source_dir` key.

2. **`datamodel/code_tool.py` — filename constant + imports.**
   Add `TOOL_CODE_FILENAME = "tool.py"`. Add imports: `from pathlib import Path`, and
   `SerializationInfo`, `ValidationInfo`, `model_serializer` from `pydantic`.

3. **`datamodel/code_tool.py` — before-validator reads `tool.py` on load.**
   Add a `@model_validator(mode="before")` classmethod that, only when
   `info.context.get("loading_from_file")` is set and `data` is a dict without a `code` key,
   reads `<source_dir>/tool.py` into `data["code"]`. If `source_dir` is missing from context
   raise a clear `ValueError`; if the file is missing/unreadable raise a `ValueError` naming
   the expected file path. The injected string then flows through the existing `validate_code`
   trio unchanged.

   ```python
   @model_validator(mode="before")
   @classmethod
   def _read_code_file(cls, data: Any, info: ValidationInfo) -> Any:
       ctx = info.context or {}
       if ctx.get("loading_from_file") and isinstance(data, dict) and "code" not in data:
           src = ctx.get("source_dir")
           if src is None:
               raise ValueError(
                   "Cannot load CodeTool: source_dir missing from load context"
               )
           code_path = Path(src) / TOOL_CODE_FILENAME
           try:
               data["code"] = code_path.read_text(encoding="utf-8")
           except OSError as e:
               raise ValueError(
                   f"code_tool.kiln at {src} is missing its {TOOL_CODE_FILENAME} "
                   f"(expected at {code_path}): {e}"
               ) from e
       return data
   ```

4. **`datamodel/code_tool.py` — wrap serializer writes `tool.py`, omits `code` from `.kiln`.**
   Add a `@model_serializer(mode="wrap")` that calls the default handler, then — only when
   the save context (`save_attachments` + `dest_path`) is present — writes `self.code` to
   `<dest_path>/tool.py` (UTF-8, verbatim) and pops `code` from the serialized dict. Without
   that context (normal `model_dump` / API responses) it leaves `code` in place and writes
   nothing.

   ```python
   @model_serializer(mode="wrap")
   def _serialize(self, handler, info: SerializationInfo) -> dict[str, Any]:
       data = handler(self)
       ctx = info.context or {}
       if ctx.get("save_attachments") and ctx.get("dest_path"):
           dest = Path(ctx["dest_path"])
           (dest / TOOL_CODE_FILENAME).write_text(self.code, encoding="utf-8")
           data.pop("code", None)
       return data
   ```

## Tests

Added to `libs/core/kiln_ai/datamodel/test_code_tool.py`:

- `test_save_writes_tool_py_and_omits_code_from_kiln` — after save, `tool.py` exists beside
  `code_tool.kiln` with byte-exact code; the raw `code_tool.kiln` JSON has no `code` key.
- `test_load_reconstructs_code_from_file` — round-trip load repopulates `code` from `tool.py`
  and all other fields survive (extends/augments the existing round-trip test).
- `test_missing_tool_py_fails_load` — deleting `tool.py` then loading raises an error naming
  `tool.py`.
- `test_corrupted_tool_py_fails_validator_on_load` — hand-writing a `tool.py` with no `run`
  surfaces the normal `validate_code` error on load.
- `test_save_is_idempotent` — saving an unchanged loaded artifact twice yields byte-identical
  `tool.py` and `code_tool.kiln`.
- `test_clone_writes_fresh_tool_py` — a clone (new id/folder) writes its own `tool.py`; the
  original's file is untouched.
- `test_delete_removes_folder_including_tool_py` — `delete()` removes the artifact folder and
  its `tool.py`.
- `test_api_dump_keeps_code` — `model_dump()` / `model_dump_json()` without the save context
  still include `code`, and writes no file.
- `test_other_model_loads_unaffected_by_source_dir` — a non-code model (e.g. `Project`) still
  loads normally with the new `source_dir` context key present.
