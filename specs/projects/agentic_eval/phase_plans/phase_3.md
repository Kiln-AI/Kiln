---
status: complete
---

# Phase 3: Web UI

## Overview

Expose agentic judges in the web app. The LLM judge form gets a third algorithm card, **Agentic Judge**, that turns trace tools on, fetches the agentic default prompt, and filters the model picker to tool-calling models. The judge prompt help lists the `trace_overview` filter. The Test Judge pane shows a **Judge Trace** button that opens the same dialog #1938 built for the results page, and its loading text changes for agentic judges. The results renderer shows an "Agentic Judge" badge, and the judge details show "Method: Agentic Judge".

#1938's results-page link and dialog in `llm_judge_result.svelte` are kept as built (`Judge trace` link, `Dialog width="wide"`, `trace.svelte` with every message expanded). Where `ui_design.md` §2–§3 differs from it (label case, `extra_wide`, `ChatTrace`), #1938 wins, and the test pane's dialog matches #1938's.

## Steps

1. **`lib/utils/eval_types/judge_algorithm.ts` (new).** The algorithm choice and its rules, as pure functions:

   ```ts
   export type JudgeAlgorithm = "llm_as_judge" | "g_eval" | "agentic_judge"

   type JudgeModelCapabilities = Pick<ModelDetails, "supports_logprobs" | "supports_function_calling">

   // Reasons keyed by the algorithms this model can't run. Copy from ui_design.md §1.
   export function unsupported_judge_algorithms(model: JudgeModelCapabilities): Partial<Record<JudgeAlgorithm, string>>

   // G-Eval with logprobs, else LLM as Judge. Never Agentic Judge.
   export function default_judge_algorithm(model: JudgeModelCapabilities): JudgeAlgorithm

   // Keeps `current` while the model supports it; otherwise the default.
   export function judge_algorithm_for_model(current: JudgeAlgorithm | undefined, model: JudgeModelCapabilities): JudgeAlgorithm

   // The builder-input flags for test and save.
   export function judge_algorithm_request_flags(algo: JudgeAlgorithm): { g_eval: boolean; trace_tools: boolean }
   ```

2. **`lib/api/v2_eval_api.ts`.** `getDefaultLlmJudgePrompt(projectId, taskId, evalId, traceTools: boolean)` sends `query: { trace_tools: traceTools }`. `testV2EvalLlmJudge` and `createLlmJudgeConfig` already carry `trace_tools` through the regenerated `LlmJudgeBuilderInput` and `CreateLlmJudgeConfigRequest` types.

3. **`lib/components/eval_types/llm_judge_form.svelte`.**
   - `selected_algo: JudgeAlgorithm | undefined`.
   - Add the Agentic Judge entry to `evaluator_algorithms`: name "Agentic Judge", description "Reads the trace with tools, only the parts it needs. Best for long agent traces." No new markup.
   - The model-change reactive block uses `unsupported_judge_algorithms` and `judge_algorithm_for_model`, so a still-supported selection survives a model change and an unsupported one falls back to the default.
   - `AvailableModelsDropdown` settings add `requires_tool_support: selected_algo === "agentic_judge"`.
   - Default prompt: one `load_default_prompt(trace_tools)` used by `onMount` and by a reactive block that refetches when `selected_algo === "agentic_judge"` differs from the mode last requested. A response replaces `judge_prompt` and `system_prompt` each only while it still equals the last fetched default (`undefined` before the first). `show_instructions_ui`, `default_reference_keys` and `default_prompt_unavailable` follow every response, and a success clears `prompt_fetch_error`. A request counter drops responses that a newer request superseded.

4. **`lib/components/eval_types/judge_prompt_fields.svelte`.** Under the `{{ trace }}` entry, next to #1939's `format_trace` sub-bullet, add: "Add the `trace_overview` filter (e.g. `{{ trace | trace_overview }}`) for a short overview of the trace: message counts and sizes, tool calls, and previews of the first and last messages." Same markup as the `format_trace` sub-bullet. Shown for every LLM judge.

5. **`lib/components/eval_types/eval_config_builder.svelte`.**
   - `llm_selected_algo: JudgeAlgorithm | undefined`.
   - Test and save spread `judge_algorithm_request_flags(llm_selected_algo)` into the builder input, replacing `g_eval` and the hard-coded `trace_tools: false`.
   - Pass `agentic_judge={is_llm_judge && llm_selected_algo === "agentic_judge"}` to the test pane.

6. **`lib/components/eval_types/test_run/eval_test_run_pane.svelte`.**
   - New prop `agentic_judge: boolean = false`. The running state's description reads "The judge is reading the trace. This can take a minute." when it is set, and the existing "Executing the scorer on your input" otherwise.
   - In the results state, after the scores block: when `test_result.judge_trace` is set, a `btn btn-sm w-full` labelled "Judge Trace" opens a `Dialog title="Judge Trace" width="wide"` holding `TraceView` (`$lib/ui/trace/trace.svelte`) with every message index in `auto_expand_indices`, the same as #1938's results-page dialog.

7. **`lib/components/eval_types/llm_judge_result.svelte`.** Next to the G-Eval badge line, an agentic judge (`props.trace_toolset_version != null`) shows `<span class="badge badge-outline badge-xs">Agentic Judge</span> Reads the trace with tools`, the same markup. #1938's link and dialog are unchanged.

8. **`routes/(app)/specs/.../eval_configs/eval_config_instruction.svelte`.** A V2 `llm_judge` with `trace_toolset_version` set shows a "Method: Agentic Judge" line, same markup and `data-testid` as the G-Eval line. The version is not shown.

9. **Test stubs.** `create_eval_config/__tests__/llm_judge_form_stub.svelte` types `selected_algo` as `JudgeAlgorithm`.

## Component Plan

| Element | House control used | Sibling it matches | Justification if custom |
|---|---|---|---|
| Agentic Judge card | Existing algorithm card markup, as a new `evaluator_algorithms` entry | G-Eval card on the same form | The card markup (radio `input` inside a `label`) predates this change; no new markup is added. |
| Model picker tool filter | `AvailableModelsDropdown` `requires_tool_support` | Its use in the run config tools picker | |
| `trace_overview` variable entry | Same markup as #1939's `format_trace` sub-bullet | The `format_trace` sub-bullet | `font-mono font-bold` on the variable name matches every entry in the list. |
| Running-state text for agentic judges | Existing running-state description line | The same line for other judges | |
| Judge Trace button (test pane) | DaisyUI grey `btn btn-sm`, `w-full` | Run Again / Run Test, the pane's full-width buttons | |
| Judge Trace dialog (test pane) | `Dialog` (`width="wide"`) + `trace.svelte` | #1938's Judge Trace dialog on the results page | |
| "Agentic Judge" badge | Same markup as the G-Eval badge | The G-Eval badge line | |
| "Method: Agentic Judge" | Same markup as "Method: G-Eval" | The G-Eval method line | |

Vertical rhythm: every addition sits in an existing flex column (`gap-6` in the form, `gap-3` in the pane, `gap-0.5` in the result meta, block lines in the details) and carries no margins of its own.

No shared control under `lib/ui/` changes.

### Shared component decisions

The kiln-ui gate flags every edit under `lib/components/` as `SHARED_CONTROL_TOUCHED`. Each file below is one of the eval-type components `ui_design.md` names as the place for this feature. No generic control changes.

| File | Decision | Callers affected |
|---|---|---|
| `eval_types/llm_judge_form.svelte` | Gains the Agentic Judge card, the tool-support picker flag, and the default-prompt refetch with its `prompt_replaced` event. | `eval_config_builder.svelte` only. |
| `eval_types/eval_config_builder.svelte` | Sends the algorithm's request flags, passes `agentic_judge` to the test pane, and treats `prompt_replaced` as a config edit. | The create-judge route only. |
| `eval_types/judge_prompt_fields.svelte` | Lists `{{ trace \| trace_overview }}` under `{{ trace }}`, for every LLM judge. | `llm_judge_form.svelte` only. |
| `eval_types/llm_judge_result.svelte` | Shows the Agentic Judge badge line. #1938's Judge Trace link and dialog are unchanged. | The results page, through the eval-type registry. |
| `eval_types/test_run/eval_test_run_pane.svelte` | Shows the Judge Trace button and dialog whenever a test result has `judge_trace`, and takes an `agentic_judge` prop (default `false`) for the running-state caption. | `eval_config_builder.svelte`, and the spec builder's `routes/(app)/specs/[project_id]/[task_id]/spec_builder/create_spec_judge_form.svelte`. The spec builder now also shows Judge Trace when its draft test returns a judge trace. That matches `ui_design.md` §2, which applies the button to every LLM judge. It never passes `agentic_judge`, because the spec builder only writes classic judges (`ui_design.md` §5). |

## Tests

- `lib/utils/eval_types/judge_algorithm.test.ts`
  - `unsupported_judge_algorithms`: each capability combination gives the right reasons, with the exact Agentic Judge copy.
  - `default_judge_algorithm`: G-Eval with logprobs, LLM as Judge without; never Agentic Judge, even with tool calling.
  - `judge_algorithm_for_model`: keeps a supported selection (Agentic Judge, LLM as Judge on a logprobs model); falls back to the default when unsupported or unset.
  - `judge_algorithm_request_flags`: one case per algorithm.
- `lib/api/v2_eval_api.test.ts`
  - `getDefaultLlmJudgePrompt` sends the path params and `trace_tools` in the query, for `true` and `false`.
- `lib/components/eval_types/llm_judge_form.test.ts`
  - Shows the Agentic Judge card with its copy when the model supports tool calling; hides it when it doesn't.
  - Shows the algorithm section for a tool-calling model without logprobs (LLM as Judge and Agentic Judge).
  - Never selects Agentic Judge by default.
  - Model picker settings carry `requires_tool_support` only while Agentic Judge is selected.
  - Picking Agentic Judge refetches with `trace_tools=true` and replaces an unedited prompt and system prompt; switching back refetches with `false`.
  - An edited prompt is kept across a refetch, while an unedited system prompt is still replaced.
  - A stale response that arrives after a newer one is ignored.
  - The `{{ trace | trace_overview }}` entry is listed.
- `lib/components/eval_types/test_run/eval_test_run_pane.test.ts`
  - The Judge Trace button shows when the result has `judge_trace`, is a grey `btn btn-sm`, and the "Judge Trace" dialog is `wide` and holds the trace.
  - No button or dialog without `judge_trace`.
  - Running state shows the agentic text with `agentic_judge`, and the default text without.
- `lib/components/eval_types/llm_judge_result.test.ts`
  - Shows the Agentic Judge badge for `trace_toolset_version: 1`; not for classic or G-Eval judges.
- `routes/.../eval_configs/eval_config_instruction.test.ts`
  - Shows "Method: Agentic Judge" for an llm_judge with `trace_toolset_version`; no version number in the text.
- `routes/.../create_eval_config/page.test.ts` (builder)
  - Agentic Judge: test and save send `trace_tools: true, g_eval: false`.
  - G-Eval: test and save send `g_eval: true, trace_tools: false`.
  - The pane's running state shows the agentic text while an Agentic Judge test runs.
