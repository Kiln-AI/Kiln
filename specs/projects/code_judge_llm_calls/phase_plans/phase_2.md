---
status: complete
---

# Phase 2: Built-in LLM tools + registry

## Overview

Ship the two parent-side built-in tools that let a code judge (and general
callers) make model calls from a sandboxed `score()`. This phase replaces the
temporary Phase-1 stub arm in `tool_registry.py` with real `LlmTool()` /
`LlmJudgeTool()` returns, and adds the shared `run_llm_call` helper extracted
from `LlmJudgeEval.evaluate`'s non-g-eval path. No sandbox bridge, no
code-eval adapter changes, no UI (Phases 3–5). See `architecture.md` §2.

Circular-import note: `tools/` importing the adapter stack cycles
(`base_adapter` imports `tool_registry`). So all adapter/eval imports inside
`llm_tools.py` are function-local. `RunOutput` is imported from the standalone
`kiln_ai.adapters.run_output` module (no cycle) for the return annotation.

## Steps

1. New file `libs/core/kiln_ai/tools/built_in_tools/llm_tools.py`:
   - Module-level imports only from safe modules: `json`, jinja2 errors,
     `base_tool` (`KilnTool`, `ToolCallContext`, `ToolCallResult`),
     `datamodel.tool_id.KilnBuiltInToolId`,
     `datamodel.json_schema.validate_schema_dict`,
     `utils.jinja_engine` (`_template_env`, `JinjaExtractionError`),
     `adapters.run_output.RunOutput`.
   - `_DEFAULT_SYSTEM_PROMPT` — reuse the eval judge default string.
   - `async def run_llm_call(*, model, provider, system_prompt, rendered_prompt,
     output_json_schema) -> RunOutput`: function-local imports of
     `adapter_for_task`, `ModelProviderName`,
     `default_structured_output_mode_for_model_provider`, `AdapterConfig`,
     `Project`, `Task`, `PromptGenerators`, `KilnAgentRunConfigProperties`,
     `StructuredOutputMode`. Validate `provider` in `ModelProviderName`
     (ValueError otherwise). Build ephemeral `Project` + `Task`
     (`instruction=system_prompt or _DEFAULT_SYSTEM_PROMPT`,
     `output_json_schema=output_json_schema`). Compute `structured_output_mode`
     via `default_structured_output_mode_for_model_provider(..., default=json_schema,
     disallowed_modes=[function_calling, function_calling_weak])`. Build adapter
     with `KilnAgentRunConfigProperties(model_name, model_provider_name,
     prompt_id=SIMPLE, structured_output_mode=mode)` and
     `AdapterConfig(allow_saving=False, top_logprobs=None)`.
     `_, run_output = await adapter.invoke_returning_run_output(rendered_prompt)`;
     return `run_output`.
   - `_render_prompt(prompt, input_dict)` helper: `_template_env.from_string(...)`
     `.render(**input_dict)`; wrap jinja errors into a raised ValueError.
   - `LlmTool(KilnTool)` — id `KilnBuiltInToolId.LLM`, name `"llm"`, params
     schema per arch §2.2 (`additionalProperties: false`, required
     prompt/model/provider). `run`: render prompt against `input or {}`; if
     `schema` present, `validate_schema_dict(schema, require_object=True)` and
     `output_json_schema = json.dumps(schema)`, else `None`;
     `run_output = await run_llm_call(...)`; return `ToolCallResult(output =
     run_output.output if isinstance(run_output.output, str) else
     json.dumps(run_output.output))`.
   - `LlmJudgeTool(KilnTool)` — id `KilnBuiltInToolId.LLM_JUDGE`, name
     `"llm_judge"`, same params minus `schema`. `run`: guard
     `context is None or context.eval_output_schema is None` → ValueError with
     the guidance message; render prompt; `run_output = await run_llm_call(...,
     output_json_schema=context.eval_output_schema)`; function-local import
     `build_llm_as_judge_score`, `score_from_token_string`;
     `scores = build_llm_as_judge_score(run_output, score_from_token_string)`;
     return `ToolCallResult(output=json.dumps(scores))`.

2. `libs/core/kiln_ai/tools/tool_registry.py`: replace the stub
   `case KilnBuiltInToolId.LLM | KilnBuiltInToolId.LLM_JUDGE: raise ...` with two
   arms returning `LlmTool()` / `LlmJudgeTool()`. Lazy (function-local) import of
   the two classes inside the arms to keep the module import graph acyclic
   (mirrors RAG/code-tool arms).

3. `libs/core/kiln_ai/tools/test_tool_registry.py`: update
   `test_all_built_in_tools_are_registered` so LLM/LLM_JUDGE now resolve (no
   longer in the not-yet-wired set).

## Tests

New `libs/core/kiln_ai/tools/built_in_tools/test_llm_tools.py`
(patch `kiln_ai.adapters.adapter_registry.adapter_for_task` with an AsyncMock
double — no network):

- `llm` no schema → returns free-text string verbatim.
- `llm` with schema → returns `json.dumps(dict)`; asserts adapter built with a
  non-None `output_json_schema` Task.
- `llm` invalid schema (malformed) → raises.
- `llm`/`llm_judge` invalid provider → raises ValueError.
- `llm`/`llm_judge` Jinja render error (missing var) → raises.
- `llm_judge` off-context (context None / eval_output_schema None) → raises the
  guidance ValueError; adapter never called.
- `llm_judge` maps pass/fail/critical → 1.0/0.0/-1.0 and 1–5 → floats; returns a
  JSON scores string.
- `llm_judge` parity: scores equal `build_llm_as_judge_score(run_output,
  score_from_token_string)` for the same structured output.
- Registry: `tool_from_id_and_project("kiln_tool::llm")` → `LlmTool`,
  `..::llm_judge` → `LlmJudgeTool`; ids/names correct.
- `run_llm_call` returns the adapter's `run_output` (str when schema None, dict
  when set).
