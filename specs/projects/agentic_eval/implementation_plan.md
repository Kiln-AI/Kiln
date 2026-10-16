---
status: draft
---

# Implementation Plan: Agentic Eval

## Prerequisite (separate task, merged first)

Non-fatal tool errors in the model adapter, including `ToolCallError` ([architecture §4](architecture.md#4-prerequisite-non-fatal-tool-errors-in-the-adapter)). Phase 1 depends on `ToolCallError` existing.

## Phases

- [ ] **Phase 1: Trace toolset v1.**
  - The self-contained `adapters/eval/trace_tools/` package: `TraceView` canonicalization, the five tools, search with a time limit, the response limit and refusals.
  - The `trace_toolset()` dispatch and `judge_template_env()`.
  - Unit tests, golden tests with the update flag, and benchmarks.
  - No judge wiring yet.
  - Specs: [components/trace_tools_v1.md](components/trace_tools_v1.md), [architecture §3.1–3.6](architecture.md#31-trace-tools-package).
- [ ] **Phase 2: Judge integration and API.**
  - Datamodel: `LlmJudgeProperties.trace_toolset_version` and its validators, `EvalRun.judge_trace`, and `V2EvalResult.judge_trace`.
  - Jinja: the `trace_overview` placeholder filter.
  - `LlmJudgeEval`: tools, the overlay template environment, the unsupported-version skip, `JudgeContextExceededError`, and a judge trace for every mode.
  - The default agentic prompt and `materialize_llm_judge_properties`.
  - The runner saves the judge trace.
  - API: `trace_tools` on the builder input, the default-prompt query parameter, `judge_trace` in test responses, 422 on context overflow, and the prompt optimization gate.
  - Regenerate the OpenAPI client.
  - Specs: [architecture §2, §3.7–3.10](architecture.md#2-data-model-changes).
- [ ] **Phase 3: Web UI.**
  - The Agentic Judge algorithm card and its form behavior.
  - The `trace_overview` variable entry.
  - Judge Trace in the test pane and on the results page.
  - The "Agentic Judge" badge and the method line.
  - Spec: [ui_design.md](ui_design.md).
- [ ] **Phase 4: Real-provider check.**
  - Paid end-to-end agentic judge tests on a small set of OpenRouter models. Each checks that the judge calls at least one trace tool before answering, and that it returns schema-valid scores.
  - This also covers structured output combined with tools, and tool schemas with numeric bounds.
  - If any model fails, stop and bring the options to the user: a per-model structured output mode, a new model-list field, or a litellm upgrade.
  - Spec: [architecture §7.8, §8](architecture.md#78-real-providers-late-phase-paid).
