---
status: complete
---

# UI Design: Agentic Eval

The UI work is small. Four existing screens change. There are no new pages, no new judge type in the type picker, and no new template card. Implementation follows the `kiln-ui` skill: a component plan before code, house controls, and the gate.

## 1. LLM Judge Form: "Agentic Judge" Algorithm

File: `app/web_ui/src/lib/components/eval_types/llm_judge_form.svelte`, used by `eval_config_builder.svelte`.

The form's **Select Judge Algorithm** step gets a third card next to **LLM as Judge** and **G-Eval**:

| Card | Description (exact copy) |
|------|--------------------------|
| Agentic Judge | Reads the trace with tools, only the parts it needs. Best for long agent traces. |

- **Rendering.** The card is a new entry in the existing `evaluator_algorithms` list, so it reuses the existing card markup. There is no new markup.
- **Selection type.** The form's choice becomes a local union, `"llm_as_judge" | "g_eval" | "agentic_judge"`, instead of reusing the legacy `EvalConfigType`.
- **One choice, so no invalid combination.** The cards are mutually exclusive, so G-Eval with trace tools can't be picked.
- **Availability.**
  - The card is unsupported when the chosen model's `supports_function_calling` is false. The reason, in the existing `unsupported_algos` map, is: "Agentic Judge requires tool calling, which this model doesn't support."
  - Unsupported cards stay hidden, as today.
  - The section shows when more than one card is available, as today.
- **Default: unchanged.** G-Eval when the model supports logprobs, otherwise LLM as Judge. Agentic Judge is never selected automatically. If a model change makes the selected card unsupported, the selection falls back to the default.
- **Model picker.** `AvailableModelsDropdown` settings become:
  - `requires_structured_output: selected_algo !== "g_eval"` (unchanged);
  - `requires_logprobs: selected_algo === "g_eval"` (unchanged);
  - `requires_tool_support: selected_algo === "agentic_judge"` (new). The dropdown's existing behavior moves models without tool calling into "Not Recommended".
- **Default prompt.**
  - The form fetches `default_llm_judge_prompt?trace_tools=<selected_algo === "agentic_judge">`.
  - When the selection crosses between Agentic Judge and the other two, the form refetches. It replaces the judge prompt, system prompt and instructions state only if the user hasn't edited the prompt, meaning it still equals the last fetched default. An edited prompt is kept.
  - `show_instructions_ui` is recomputed from the newly fetched default, as on first load.
- **Prompt fields** (`judge_prompt_fields.svelte`): the list of template variables adds `trace | trace_overview`, described as "A short overview of the trace: message counts and sizes, tool calls, and previews of the first and last messages." It's listed for every LLM judge, since the filter works with or without tools.
- **Test and save** (`eval_config_builder.svelte`):
  - send `trace_tools: selected_algo === "agentic_judge"` and `g_eval: selected_algo === "g_eval"`;
  - extend `testV2EvalLlmJudge` and `createLlmJudgeConfig` in `v2_eval_api.ts` with `trace_tools`.

## 2. Test Run Panel: Judge Trace

File: `app/web_ui/src/lib/components/eval_types/test_run/eval_test_run_pane.svelte`.

- **The button.** When a test result has `judge_trace`, a grey `btn btn-sm` labelled **Judge Trace** appears after the scores.
- **The dialog.** The button opens a `Dialog` titled "Judge Trace" (`width="extra_wide"`) that renders `ChatTrace` (`lib/ui/trace/chat_trace.svelte`) with the judge trace and `project_id`.
- **Which judges.** This applies to every LLM judge, classic and G-Eval included.
- **Loading text.** While an Agentic Judge test runs, the pane's existing loading state reads: "The judge is reading the trace. This can take a minute."

## 3. Results Page: Judge Trace

Files: `run_result/+page.svelte` and `lib/components/eval_types/llm_judge_result.svelte`.

- **The link.** `llm_judge_result.svelte` gets a **Judge Trace** link next to its reasoning link, styled the same. It shows only when the row's `eval_run.judge_trace` is present.
- **The dialog.** It opens a `Dialog` titled "Judge Trace" (`extra_wide`) with `ChatTrace`.
- **New prop.** The results page passes `judge_trace` to the result renderer, alongside the props it already passes (`scores`, skip fields, `eval_config`, `intermediate_outputs`). Other renderers ignore it.
- **Badge.** Where the renderer shows a "G-Eval" badge today, an Agentic Judge shows an "Agentic Judge" badge, in the same style.

## 4. Judge Details

File: `eval_configs/eval_config_instruction.svelte`.

- The line that reads "Method: G-Eval" for G-Eval judges gets a sibling, **"Method: Agentic Judge"**, for judges with trace tools on. The toolset version is not shown.
- The type label stays "LLM as Judge" everywhere.

## 5. Not Changing

- **The judge-type picker** (`create_eval_config`): Agentic Judge lives inside LLM as Judge.
- **LLM Judge Templates** (`select_template`) and **the spec builder**: templates describe what to check, not how the judge reads. The judge is still created in the form above, with today's default algorithm.
- **The eval builder and copilot:** they keep writing classic judges.

## 6. Component Plan (preliminary)

The implementing agent finalizes this plan per the `kiln-ui` skill.

| Element | House control | Sibling it matches |
|---------|---------------|--------------------|
| Agentic Judge card | Existing algorithm card markup (data-driven entry) | G-Eval card on the same form |
| Judge Trace button (test pane) | DaisyUI `btn btn-sm` | Other secondary actions in the test pane |
| Judge Trace dialog | `Dialog` + `ChatTrace` | The "Trace" dialog on the results page |
| Judge Trace link (results) | Same markup as the existing reasoning link in `llm_judge_result.svelte` | The reasoning link |
| "Agentic Judge" badge | Same markup as the G-Eval badge | The G-Eval badge |
| "Method: Agentic Judge" | Same markup as "Method: G-Eval" | The G-Eval method line |
| `trace_overview` variable entry | Same markup as the existing variable entries | The `trace` variable entry |

No shared control under `lib/ui/` changes.
