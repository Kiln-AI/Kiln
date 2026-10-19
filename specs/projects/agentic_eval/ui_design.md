---
status: complete
---

# UI Design: Agentic Eval

The UI work is small. Four existing screens change. There are no new pages, no new judge type in the type picker, and no new template card. Implementation follows the `kiln-ui` skill: a component plan before code, house controls, and the gate.

## 1. LLM Judge Form: "Agentic Judge" Algorithm

File: `app/web_ui/src/lib/components/eval_types/llm_judge_form.svelte`, used by `eval_config_builder.svelte`. The algorithm rules are pure functions in `lib/utils/eval_types/judge_algorithm.ts`.

The form's **Select Judge Algorithm** step is a radio list: one row per algorithm, with the radio on the left and the title over the description. Agentic Judge is the third option, after **LLM as Judge** and **G-Eval Judge**:

| Option | Description (exact copy) |
|--------|--------------------------|
| Agentic Judge | Reads the trace with tools, only the parts it needs. Best for long agent traces. |

- **Rendering.** The list is a `FormElement` with `inputType="radio"`, the same control as "Match Mode" on the Tool Call Check form. Each algorithm is an entry in `evaluator_algorithms`, so Agentic Judge adds no markup.
- **Selection type.** The choice is `JudgeAlgorithm` (`"llm_as_judge" | "g_eval" | "agentic_judge"`, in `judge_algorithm.ts`), not the legacy `EvalConfigType`.
- **One choice, so no invalid combination.** The options are mutually exclusive, so G-Eval with trace tools can't be picked.
- **Availability.**
  - The option is unsupported when the chosen model's `supports_function_calling` is false. The reason, from `unsupported_judge_algorithms`, is: "Agentic Judge requires tool calling, which this model doesn't support."
  - Unsupported options stay hidden, as today.
  - The section shows when more than one option is available, as today.
- **Default: unchanged.** G-Eval when the model supports logprobs, otherwise LLM as Judge. Agentic Judge is never selected automatically. Only an algorithm the user picked survives a model change, and only while the new model supports it. Otherwise the selection is the new model's default.
- **Model picker.** `AvailableModelsDropdown` settings become:
  - `requires_structured_output: selected_algo !== "g_eval"` (unchanged);
  - `requires_logprobs: selected_algo === "g_eval"` (unchanged);
  - `requires_tool_support: selected_algo === "agentic_judge"` (new). The dropdown's existing behavior moves models without tool calling into "Not Recommended".
- **Default prompt.**
  - The form fetches `default_llm_judge_prompt?trace_tools=<selected_algo === "agentic_judge">`.
  - When the selection crosses between Agentic Judge and the other two, the form refetches. The judge prompt and the system prompt are checked separately: a field that still equals the last fetched default takes the new default, and an edited field is kept. A response that a newer request superseded is dropped.
  - `show_instructions_ui` is recomputed from the newly fetched default, as on first load.
  - When a refetch replaces a prompt, the form fires `prompt_replaced`. The builder treats it as a config edit, so an earlier test no longer counts as passed.
  - If a fetch fails, each unedited field is cleared and the form shows "Could not load default judge prompt. The server will use its default." A test then sends no prompt, so the server builds the default for the selected algorithm. The required Judge Prompt field blocks Save until the user writes one.
- **Prompt fields** (`judge_prompt_fields.svelte`): under the `{{ trace }}` entry, next to the `format_trace` sub-bullet, the variable list adds the `trace_overview` filter (`{{ trace | trace_overview }}`), described as "a short overview of the trace: message counts and sizes, tool calls, and previews of the first and last messages." It's listed for every LLM judge, since the filter works with or without tools.
- **Test and save** (`eval_config_builder.svelte`):
  - send the flags from `judge_algorithm_request_flags`: `trace_tools: selected_algo === "agentic_judge"` and `g_eval: selected_algo === "g_eval"`;
  - `testV2EvalLlmJudge` and `createLlmJudgeConfig` in `v2_eval_api.ts` carry `trace_tools` through the generated API types. `getDefaultLlmJudgePrompt` takes it as an argument.

## 2. Test Run Panel: Judge Trace

File: `app/web_ui/src/lib/components/eval_types/test_run/eval_test_run_pane.svelte`.

- **The button.** When a test result has `judge_trace`, a grey, full-width `btn btn-sm w-full` labelled **Judge Trace** appears after the scores.
- **The dialog.** The button opens a `Dialog` titled "Judge Trace" (`width="wide"`) that renders the judge trace with `TraceView` (`lib/ui/trace/trace.svelte`), every message expanded. It is the same dialog as on the results page (§3).
- **Which judges.** This applies to every LLM judge, classic and G-Eval included. The spec builder's draft test uses the same pane, so it shows the button too.
- **Loading text.** While an Agentic Judge test runs, the pane's existing loading state reads: "The judge is reading the trace. This can take a minute."

## 3. Results Page: Judge Trace

Files: `run_result/+page.svelte` and `lib/components/eval_types/llm_judge_result.svelte`.

- **The link.** When the row's `eval_run.judge_trace` is present, `llm_judge_result.svelte` shows a **Judge trace** link in place of its "View reasoning" link, styled the same. Rows without a judge trace keep the reasoning link.
- **The dialog.** It opens a `Dialog` titled "Judge Trace" (`width="wide"`) with `TraceView` (`lib/ui/trace/trace.svelte`), every message expanded.
- **New prop.** The results page passes `judge_trace` to the result renderer, alongside the props it already passes (`scores`, skip fields, `eval_config`, `intermediate_outputs`). Other renderers ignore it.
- **Badge.** Next to where the renderer shows the "G-Eval" badge line, an Agentic Judge shows an "Agentic Judge" badge with the caption "Reads the trace with tools", in the same markup as G-Eval's "Chain-of-thought scoring" line.

## 4. Judge Details

File: `eval_configs/eval_config_instruction.svelte`.

- The line that reads "Method: G-Eval" for G-Eval judges gets a sibling, **"Method: Agentic Judge"**, for judges with trace tools on. The toolset version is not shown.
- The type label stays "LLM as Judge" everywhere.

## 5. Not Changing

- **The judge-type picker** (`create_eval_config`): Agentic Judge lives inside LLM as Judge.
- **LLM Judge Templates** (`select_template`) and **the spec builder**: templates describe what to check, not how the judge reads. The judge is still created in the form above, with today's default algorithm.
- **The eval builder and copilot:** they keep writing classic judges.

## 6. Component Plan

| Element | House control | Sibling it matches |
|---------|---------------|--------------------|
| Agentic Judge option | `FormElement` radio list (`inputType="radio"`), as a new `evaluator_algorithms` entry | "Match Mode" on the Tool Call Check form |
| Judge Trace button (test pane) | DaisyUI grey `btn btn-sm w-full` | Run Test and Run Again, the pane's full-width buttons |
| Judge Trace dialog (test pane) | `Dialog` (`width="wide"`) + `TraceView` (`trace.svelte`), every message expanded | The Judge Trace dialog on the results page |
| Judge trace link (results) | Same markup as the reasoning link in `llm_judge_result.svelte` | The reasoning link |
| "Agentic Judge" badge | Same markup as the G-Eval badge line | The G-Eval badge line |
| "Method: Agentic Judge" | Same markup as "Method: G-Eval" | The G-Eval method line |
| `trace_overview` variable entry | Same markup as the `format_trace` sub-bullet | The `format_trace` sub-bullet under `{{ trace }}` |

No shared control under `lib/ui/` changes.
