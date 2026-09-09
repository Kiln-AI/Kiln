---
status: complete
---

# Phase 1: Datamodel foundations

## Overview

Additive datamodel groundwork for letting code-judge evals call LLM tools from
their sandboxed `score()`. Zero data migration — every change is a new field,
new enum member, or new validator. No tools, bridge, adapter, or UI here (later
phases). See `architecture.md` §1.

## Steps

1. `libs/core/kiln_ai/datamodel/eval.py` — `CodeEvalProperties`:
   - Bump `timeout_seconds` default `30 → 180` (bounds stay `ge=1, le=300`).
   - Add `tool_allowlist: list[ToolId] = Field(default_factory=list)`.
   - Add a `validate_allowlist` model-validator ported from `CodeTool`: reject
     `SKILL_TOOL_ID_PREFIX`, reject `KILN_UNMANAGED_TOOL_ID_PREFIX`, reject
     duplicates. OMIT the self-reference check (a code eval is not a tool).
   - Import `ToolId`, `SKILL_TOOL_ID_PREFIX`, `KILN_UNMANAGED_TOOL_ID_PREFIX`
     from `kiln_ai.datamodel.tool_id`.

2. `libs/core/kiln_ai/datamodel/tool_id.py` — `KilnBuiltInToolId`: add
   `LLM = "kiln_tool::llm"` and `LLM_JUDGE = "kiln_tool::llm_judge"`. They
   validate through the existing built-in membership branch of `_check_tool_id`
   with no new parsing.

3. `libs/core/kiln_ai/tools/base_tool.py` — `ToolCallContext`: add
   `eval_output_schema: str | None = None` (additive, defaulted).

4. (Required side effect, not in original 3-file scope) `tool_registry.py`:
   `tool_from_id_and_project` uses an exhaustive `match` guarded by
   `raise_exhaustive_enum_error`. Adding enum members without arms breaks
   `ty check` (and `test_all_built_in_tools_are_registered`). Add a single
   not-yet-wired arm `case KilnBuiltInToolId.LLM | KilnBuiltInToolId.LLM_JUDGE:`
   that raises `ValueError("... not yet resolvable ...")`. The real
   `LlmTool()` / `LlmJudgeTool()` returns land in Phase 2 (arch §2.4).

## Tests

- `test_eval_model.py::TestCodeEvalPropertiesValidation`:
  - timeout default is now 180.
  - `tool_allowlist` default empty; valid allowlist accepted (incl. new
    `kiln_tool::llm` / `kiln_tool::llm_judge`).
  - allowlist rejects skill IDs, unmanaged IDs, duplicates, invalid IDs.
  - allowlist ALLOWS a code-tool self-referential ID (no self-ref check).
- `test_tool_id.py::TestKilnBuiltInToolId`: `LLM` / `LLM_JUDGE` enum values;
  round-trip through `_check_tool_id` and the `ToolId` pydantic validator;
  membership.
- `test_base_tools.py::TestToolCallContext`: default `eval_output_schema is
  None`; can be set alongside `allow_saving`.
- `test_tool_registry.py::test_all_built_in_tools_are_registered`: updated so
  the two not-yet-wired IDs are asserted to raise until Phase 2.
