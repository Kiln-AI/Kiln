---
status: complete
---

# UI Design: Eval Builder cases grounded in an OpenEnv server

Everything here applies to a multi-turn build whose run config reaches one OpenEnv server. Any other
build looks and behaves exactly as today.

The builder keeps its steps (describe, clarify, refine, generate, review, save). The changes are:
one more model requirement in Generation Settings, one more progress stage, a new screen for
dropped cases, a read-only section in review, and a note where users write judges.

Names below are the ones in `builder/+page.svelte` today.

## Generation Settings

The dialog keeps its lanes. Only the Judge Model lane changes.

- **Tool support.** On an OpenEnv build, the lane's `AvailableModelsDropdown` adds
  `requires_tool_support: true` to its settings (`requires_structured_output: true,
  suggested_mode: "evals"` stay). The dropdown already moves unsupported models to "Not
  Recommended - Tool Calling Not Supported" and warns when one is selected; nothing new to build.
- **Default.** Unchanged: the last saved eval's judge, else the first suggested model. A remembered
  judge without tool support shows the dropdown's existing warning.

## Progress: checking cases

A new phase, `grounding_cases`, runs after "Creating Simulated Users" and before the conversations
are driven.

- Same takeover as the other phases: `ConversationAnimation` with title "Checking Cases Against
  Your Environment" and description "Kiln's agent looks inside the OpenEnv server to fit each case
  to real data and write what the judge should check."
- Below it, `ProgressCount` with `noun="cases checked"`, `max` = the number of cases, and a
  dropped count in the slot `failed` uses today, labelled "dropped" (a new `failed_label` prop,
  default "failed").
- Counts come from the grounding stream, one event per finished case.
- Cancelling (leaving the page, or Back) aborts the stream; the server ends every open episode.

## Dropped cases

The screen appears after grounding when at least one case dropped. It replaces today's partial-stop
text for this case only; drive failures later in the pipeline keep today's screen.

Layout, top to bottom:

- Title: "Some Cases Don't Fit Your Environment".
- One line: "Kiln checked each case against your OpenEnv server. 3 of 20 couldn't be made to fit."
- The dropped cases, one row each: the planned scenario (one line, clamped, "See all" opens it),
  and under it the reason in muted text. The reason is the grounding agent's `drop_detail`, as
  written. No reason codes on screen.
- Buttons, right-aligned, primary last:
  - **Cancel**: back to the plan, discarding this batch's cases.
  - **Retry**: plans the batch again with the dropped scenarios and their reasons added to the
    planner guidance, then runs the whole flow again (simulated users, checking, conversations).
    The Refine Plan steer, if any, is kept.
  - **Continue With 17** (primary): drives and reviews the 17 cases that fit.
- When every case dropped: the same screen without Continue, and the line reads "None of the 20
  cases could be made to fit."

Nothing about dropped cases is shown after Continue.

## Review ("Align the Judge")

Nothing on this screen edits a case, and that stays true.

- In the Overview panel of `ClaimEvidenceReview`, under the conversation output, a collapsed
  section **"Environment and Judge Guidance"**, closed by default.
- Open, it shows:
  - **Starting state**: the case's reset arguments as a small key-value list (nested keys by path,
    `startup.acting_user`), `setup_sql` in a code block clamped to a few lines with "Show All".
  - **Judge guidance**: the rendered markdown (Starting point, Facts with their tool call,
    Expected outcome).
- Read-only. Shown only for grounded cases, which on an OpenEnv build is every case.

## Writing a judge later

On the judge creation form (`create_eval_config`), when the eval has an OpenEnv server, a note above
the prompt fields:

> This eval's cases were checked against your OpenEnv server. Each one has judge guidance: the
> facts of the environment the agent worked in and the correct answer. Use it in your prompt as
> `{{ reference_data.judge_guidance }}`.

Rough placement for v1; to be polished later.

## Not in this design

- The project-wide multi-turn synthetic user guide's editor (Sam is scoping it).
- Showing or changing the eval's OpenEnv server on the eval page (follow-up).
