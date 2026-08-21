---
status: complete
---

# Phase 5: UI, examples & schema

## Overview

Phase 5 is the author-facing surface for the code-judge LLM tools shipped in
phases 1–4. It makes `llm` / `llm_judge` selectable in the tool picker, adds an
allowlist picker to the code-eval form (bound to `properties.tool_allowlist`),
adds two editor examples demonstrating `tools.llm_judge` and the cheap-triage
`tools.llm` + `tools.llm_judge` pattern (mirrored byte-for-byte in the sandbox
sample tests), and surgically patches the OpenAPI schema (stopgap; canonical
regen deferred to the user).

## Steps

1. **Backend catalog** (`app/desktop/studio_server/tool_api.py`,
   `get_available_tools`): add an always-available `ToolSetType.BUILTIN` set
   ("AI Models") listing `KilnBuiltInToolId.LLM` and `KilnBuiltInToolId.LLM_JUDGE`
   (not demo-gated). Update the tool_api tests that assert no builtin set exists.
2. **llm_judge scoping**: add a `code_eval_context: boolean` (default false) to
   `ToolsSelectorSettings`; `ToolsSelector.get_tool_options` filters
   `kiln_tool::llm_judge` from the picker unless the consumer opts in. Only the
   code-eval form opts in — everywhere else `llm_judge` is hidden (it errors
   off-context at runtime per functional_spec §6, so this is defense-in-UI, not
   the only guard). `llm` is always shown.
3. **Allowlist picker** (`code_eval_form.svelte`): add `export let project_id`,
   bind a `ToolsSelector` (with `code_eval_context: true`) to
   `properties.tool_allowlist`, and include `tool_allowlist` in `getProperties()`.
   Pass `{project_id}` from `eval_config_builder.svelte`.
4. **Editor examples** (`code_eval_helpers.ts`, `generate_examples`): append
   "LLM judge" (static, judge auto-uses eval schema) and "Triage then LLM judge"
   (dynamic safe-branch via `build_return_dict`) examples.
5. **Schema stopgap** (`app/web_ui/src/lib/api_schema.d.ts`): add
   `tool_allowlist?: string[]` to `CodeEvalProperties`; bump `timeout_seconds`
   annotation `@default 30` → `@default 180`. Nothing else.

## Tests

- Python `test_code_eval_samples.py`: byte-exact mirrors of the two new examples
  executed through the real sandbox with a stubbed `adapter_for_task` judge
  (schema-routing factory for the triage example's two tool calls).
- Python `test_tool_api.py`: builtin set present with `llm` + `llm_judge`; update
  the four tests that assumed no builtin set.
- Web `code_eval_form.test.ts`: allowlist `ToolsSelector` binds to
  `tool_allowlist` (via a stub); five example tabs incl. the new labels.
- Web `code_eval_helpers.test.ts`: `generate_examples` returns 5 with the new
  labels; new snippets contain `tools.llm_judge` / `tools.llm`.
