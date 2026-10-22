---
status: complete
---

# Implementation Plan: Agentic Eval

## Base: Stacked PRs

This branch is stacked on three open PRs, merged in with merge commits:

- [Kiln-AI/Kiln#1937](https://github.com/Kiln-AI/Kiln/pull/1937), which includes [Kiln-AI/Kiln#1934](https://github.com/Kiln-AI/Kiln/pull/1934): non-fatal tool errors and `ToolCallError` ([architecture §4](architecture.md#4-prerequisite-non-fatal-tool-errors-in-the-adapter)). Phase 1 depends on `ToolCallError`.
- [Kiln-AI/Kiln#1938](https://github.com/Kiln-AI/Kiln/pull/1938): `V2EvalResult.judge_trace`, `EvalRun.judge_trace`, the runner saving it, `LlmJudgeEval` returning `judge_run.trace`, and the "Judge trace" link and dialog in `llm_judge_result.svelte` on the results page.
- [Kiln-AI/Kiln#1939](https://github.com/Kiln-AI/Kiln/pull/1939): the default judge prompt reads `{{ trace | format_trace }}`, has no task description block, words its steps by turn mode, and adds the `{{ system_prompt }}` variable.

What those PRs already built is kept as they built it. Phases 2 and 3 add only what is still missing from the spec. Where the spec and those PRs differ in a detail (a label, a dialog width, the trace viewer), the PRs win, so this branch doesn't rewrite a teammate's open work.

## Phases

- [x] **Phase 1: Trace toolset v1.**
  - The self-contained `adapters/eval/trace_tools/` package: `TraceView` canonicalization, the five tools, search with a time limit, the response limit and refusals.
  - The `trace_toolset()` dispatch and `judge_template_env()`.
  - Unit tests, golden tests with the update flag, and benchmarks.
  - No judge wiring yet.
  - Specs: [components/trace_tools_v1.md](components/trace_tools_v1.md), [architecture §3.1–3.6](architecture.md#31-trace-tools-package).
- [x] **Phase 2: Judge integration and API.**
  - Datamodel: `LlmJudgeProperties.trace_toolset_version` and its validators. `EvalRun.judge_trace` and `V2EvalResult.judge_trace` come from #1938; add only the `materialize_lazy_content` validator on `EvalRun.judge_trace` if it is still missing.
  - Jinja: the `trace_overview` placeholder filter.
  - `LlmJudgeEval`: tools, the overlay template environment, the unsupported-version skip, and `JudgeContextExceededError`. The judge trace itself comes from #1938.
  - The default agentic prompt, built on #1939's prompt builder, and `materialize_llm_judge_properties`. Its steps must not point to a `<trace>` tag, because the agentic prompt has none.
  - API: `trace_tools` on the builder input, the default-prompt query parameter, `judge_trace` in test responses, 422 on context overflow, and the prompt optimization gate.
  - Regenerate the OpenAPI client.
  - Specs: [architecture §2, §3.7–3.10](architecture.md#2-data-model-changes).
- [x] **Phase 3: Web UI.**
  - The Agentic Judge algorithm card and its form behavior.
  - The `trace_overview` variable entry.
  - Judge Trace in the test pane. The results-page link comes from #1938.
  - The "Agentic Judge" badge and the method line.
  - Spec: [ui_design.md](ui_design.md).
- [x] **Phase 4: Real-provider check.**
  - Paid end-to-end agentic judge tests on a small set of OpenRouter models. Each checks that the judge calls at least one trace tool before answering, and that it returns schema-valid scores.
  - This also covers structured output combined with tools, and tool schemas with numeric bounds.
  - If any model fails, stop and bring the options to the user: a per-model structured output mode, a new model-list field, or a litellm upgrade.
  - Spec: [architecture §7.8, §8](architecture.md#78-real-providers-late-phase-paid).
