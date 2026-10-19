---
status: complete
---

# Phase 2: Code judge file storage

## Overview

Give `CodeEvalProperties` the same treatment Phase 1 gave `CodeTool`: move the
user-authored Python `score()` source out of `eval_config.kiln` JSON and into a
fixed-name sibling file `scorer.py` in the eval-config folder. The in-memory
`code: str` field is unchanged — it is read from `scorer.py` on load (before
validators run) and written to `scorer.py` on disk-save, with `code` omitted
from the serialized `properties` in `eval_config.kiln` but kept in normal / API
model dumps.

The twist versus Phase 1: `CodeEvalProperties` is **not** a top-level
`KilnParentedModel`. It is a `BaseModel` member of the `V2EvalConfigProperties`
discriminated union (`Discriminator("type")`), nested inside
`EvalConfig.properties`. It is never saved on its own — it is serialized and
validated as part of `EvalConfig`. So the file read/write happens for a nested
union member, driven by the load/save context that `EvalConfig.load_from_file` /
`save_to_file` set on the parent. The whole phase hinges on Pydantic
propagating that context down to the nested union member (architecture §3.3,
risk §9).

The base-model load-context change (`source_dir`) already landed in Phase 1
(`basemodel.py:436`), and the save side already passes `dest_path` — no
base-model change is needed here. The execution engine and sandbox are
untouched: nothing adds the artifact folder to `sys.path` or imports
`scorer.py`. Storage only.

## Steps

0. **FIRST — verify context propagation to discriminated-union members.**
   Before writing any production code, confirm (via a throwaway probe mirroring
   the `Discriminator("type")` union shape of `EvalConfig.properties`) that
   Pydantic 2.13 propagates:
   - the **validation** context (`loading_from_file` / `source_dir`) to a nested
     union member's `mode="before"` validator, and
   - the **serialization** context (`save_attachments` / `dest_path`) to a nested
     union member's `mode="wrap"` serializer, via both `model_dump` and
     `model_dump_json` (the latter is what `save_to_file` uses), and
   - that a **context-less** dump still keeps `code` (API-dump behavior).

   If any of these do NOT propagate, STOP and return a roadblock — do not invent
   a workaround. (Result: all four verified to propagate on pydantic 2.13.4.)

1. **`datamodel/eval.py` — filename constant + imports.**
   Add `SCORER_CODE_FILENAME = "scorer.py"` near the top of the module. Add
   `from pathlib import Path`. Extend the existing `pydantic` import to also
   bring in `SerializationInfo`, `SerializerFunctionWrapHandler`, and
   `model_serializer` (the module already imports `ValidationInfo` and
   `model_validator`).

2. **`datamodel/eval.py` — before-validator on `CodeEvalProperties` reads
   `scorer.py` on load.**
   Add a `@model_validator(mode="before")` classmethod that, only when
   `info.context.get("loading_from_file")` is set and `data` is a dict without a
   `code` key, reads `<source_dir>/scorer.py` into `data["code"]`. If
   `source_dir` is missing from context raise a clear `ValueError`; if the file
   is missing/unreadable raise a `ValueError` naming the expected file path. The
   injected string then flows through the existing `validate_code` trio
   unchanged. Mirrors `CodeTool._read_code_file`.

   ```python
   @model_validator(mode="before")
   @classmethod
   def _read_code_file(cls, data: Any, info: ValidationInfo) -> Any:
       ctx = info.context or {}
       if (
           ctx.get("loading_from_file")
           and isinstance(data, dict)
           and "code" not in data
       ):
           src = ctx.get("source_dir")
           if src is None:
               raise ValueError(
                   "Cannot load CodeEvalProperties: source_dir missing from load context"
               )
           code_path = Path(src) / SCORER_CODE_FILENAME
           try:
               data["code"] = code_path.read_text(encoding="utf-8")
           except OSError as e:
               raise ValueError(
                   f"eval_config.kiln at {src} is missing its {SCORER_CODE_FILENAME} "
                   f"(expected at {code_path}): {e}"
               ) from e
       return data
   ```

3. **`datamodel/eval.py` — wrap serializer on `CodeEvalProperties` writes
   `scorer.py`, omits `code` from the serialized `properties`.**
   Add a `@model_serializer(mode="wrap")` that calls the default handler, then —
   only when the save context (`save_attachments` + `dest_path`) is present —
   writes `self.code` to `<dest_path>/scorer.py` (UTF-8, verbatim) and pops
   `code` from the serialized dict. Without that context (normal `model_dump` /
   API responses) it leaves `code` in place and writes nothing. The default
   handler preserves `type` (needed by the discriminator), `reference_keys`, and
   `timeout_seconds`. Mirror the Phase 1 serialization-schema trade-off comment
   (do not delete the serializer to "fix" the collapsed serialization-mode
   schema).

   ```python
   @model_serializer(mode="wrap")
   def _serialize(
       self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
   ) -> dict[str, Any]:
       data = handler(self)
       ctx = info.context or {}
       if ctx.get("save_attachments") and ctx.get("dest_path"):
           dest = Path(ctx["dest_path"])
           if not dest.is_dir():
               raise ValueError(
                   f"dest_path must be an existing directory when saving code, got: {dest}"
               )
           (dest / SCORER_CODE_FILENAME).write_text(self.code, encoding="utf-8")
           data.pop("code", None)
       return data
   ```

4. **`datamodel/eval.py` — surface nested load errors past the outer union
   (constraint discovered during Step 0 follow-through).**
   Context propagation to the nested member works (Step 0), and the happy-path
   round-trip works. But `EvalConfig.properties` is typed
   `V2EvalConfigProperties | dict[str, Any] | None`, and Pydantic's smart union
   *recovers* from a nested-member validation error by falling back to the
   `dict` branch. So when `CodeEvalProperties._read_code_file` raises (missing
   scorer.py) or `validate_code` raises (corrupt scorer.py), the real error is
   swallowed and re-surfaces as the generic `EvalConfig` after-validator message
   "V2 config requires typed properties" — violating functional spec §2.2/§4
   (clear error naming the file / the validator error). This masking is
   **pre-existing** (it already hides inline-code syntax errors today); Phase 2
   just makes it matter.

   Fix at the load boundary in `EvalConfig.dispatch_properties_parsing` (the
   existing `mode="before"` validator that already dispatches properties
   parsing): when `config_type == "v2"`, `loading_from_file` is set, and
   `properties` is a `code_eval` dict, eagerly parse it via
   `CodeEvalProperties.model_validate(props, context=ctx)`. That runs
   `_read_code_file` (reads scorer.py via the propagated context) and the trio
   directly, so any error surfaces instead of being masked; on success it
   assigns the typed instance, which the union accepts without re-validation.
   The reader stays on `CodeEvalProperties` (architecture-faithful); this is a
   minimal, load-only, code_eval-scoped tweak. In-memory dict construction is
   left unchanged (pre-existing behavior).

5. **`datamodel/eval.py` — `__get_pydantic_json_schema__` override on
   `CodeEvalProperties` (CR-Critical fix).**
   Unlike `CodeTool` (which is never a FastAPI `response_model`),
   `CodeEvalProperties` is nested in `EvalConfig`, and `EvalConfig` IS the
   declared `response_model` on several `eval_api.py` endpoints. FastAPI
   generates response schemas in *serialization* mode, and the wrap serializer
   (Step 3) returns an untyped `dict`, so the serialization-mode JSON schema
   collapses to `{additionalProperties: true, type: object}` — dropping `code`
   and splitting the component (`CodeEvalProperties-Output`). That drifts the
   committed `app/web_ui/src/lib/api_schema.d.ts` (breaking `check_schema.sh`,
   checks.sh:155) and the web types that key off
   `components["schemas"]["CodeEvalProperties"]`. The Phase-1
   "documented-comment-only" mitigation is INSUFFICIENT for this model.

   Add a `__get_pydantic_json_schema__` classmethod that recursively strips the
   `serialization` core-schema entries before delegating to the handler, so
   JSON-schema generation uses the field-based (validation) representation in
   both modes. The strip must be recursive: the before/after validators wrap the
   `model` core schema (which carries the serializer's `serialization` entry) in
   `function-before` / `function-after` schemas, so the entry is not at the top
   level. This affects only schema generation, never runtime (de)serialization.
   Result: serialization-mode schema == validation-mode schema; a single,
   fully-typed `CodeEvalProperties` component; no OpenAPI drift. Also correct the
   serializer docstring, which (copied from Phase 1) wrongly asserted no endpoint
   references this model's serialization schema.

No change to `validate_code` (the trio) or the `V2EvalConfigProperties` union.
Other eval-config property types (`LlmJudgeProperties`, etc.) have no such
serializer, so they write no sibling file — satisfying the "only code-eval
configs write scorer.py" invariant automatically.

## Tests

Added to `libs/core/kiln_ai/datamodel/test_eval_model.py` (the datamodel eval
test file). A small helper builds a saved `Task -> Eval -> EvalConfig(v2,
CodeEvalProperties)` hierarchy on disk.

- `test_context_propagates_to_nested_union_member` — regression lock for the
  Phase-2 hinge mechanism: an `EvalConfig(v2, CodeEvalProperties)` saved and
  reloaded round-trips `code` (validation context reached the nested member),
  and the serialized `properties` omit `code` (serialization context reached the
  nested member). Asserts the mechanism the whole phase depends on.
- `test_save_writes_scorer_py_and_omits_code_from_properties` — after
  `EvalConfig.save_to_file()`, `scorer.py` exists beside `eval_config.kiln` with
  byte-exact code; the raw `eval_config.kiln` JSON's `properties` has no `code`
  key but keeps `type` / `reference_keys` / `timeout_seconds`.
- `test_load_reconstructs_code_from_scorer_py` — round-trip load repopulates
  `code` from `scorer.py` and other `CodeEvalProperties` fields survive.
- `test_missing_scorer_py_fails_load` — deleting `scorer.py` then loading raises
  an error naming `scorer.py`.
- `test_corrupted_scorer_py_fails_validator_on_load` — hand-writing a
  `scorer.py` with no `score` function surfaces the normal `validate_code` error
  on load.
- `test_save_is_idempotent` — saving an unchanged loaded config twice yields
  byte-identical `scorer.py` and `eval_config.kiln`.
- `test_api_dump_keeps_code` — `model_dump()` / `model_dump_json()` of a
  `CodeEvalProperties` (and of the parent `EvalConfig`) without the save context
  still include `code`, and write no file.
- `test_source_dir_missing_from_load_context_fails` — defensive guard:
  `loading_from_file` set but `source_dir` absent fails clearly.
- `test_serialize_rejects_non_directory_dest_path` — save context with a
  non-directory `dest_path` fails clearly.
- `test_other_eval_type_writes_no_sibling_file` — an `EvalConfig(v2,
  LlmJudgeProperties)` (and a legacy g_eval config) saves with no `scorer.py`
  written beside `eval_config.kiln`.
- `test_inline_code_in_properties_is_lenient` — a `properties` dict that already
  carries `code` (in-memory `model_validate` with load context) uses it as-is and
  does not touch disk (graceful-construction property, functional spec §7).
- `test_serialization_schema_matches_validation_schema` — locks in the Step-5
  fix at the model level: `model_json_schema(mode="serialization")` equals
  `mode="validation")` and keeps `code` typed (no collapse). No FastAPI needed.
- `test_openapi_component_is_single_and_typed` — reproduces the reviewer's check:
  a minimal FastAPI app with `response_model=EvalConfig` emits a single,
  fully-typed `CodeEvalProperties` component (no `-Input`/`-Output` split, `code`
  present). Proves the committed `api_schema.d.ts` would not drift.
