---
status: complete
---

# UI Design: Eval Builder cases grounded in an OpenEnv server

Everything here applies to a multi-turn build whose run config reaches one OpenEnv server. Any other
build looks and behaves exactly as today.

The builder keeps its steps (describe, clarify, refine, generate, review, save). The changes are:
one more model requirement in Generation Settings, one more progress stage, a notice in review
when cases were dropped, a read-only section in review, and a note where users write judges.

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

A dropped case doesn't stop the build. The cases that fit are driven, and the review says what was
dropped. Drive failures later in the pipeline keep today's screen.

### Notice over the review

Shown once, over the first Step 5 screen, when the review opens after a drive whose grounding
dropped some cases. A `Dialog`, laid out like the Improve Judge dialog:

- Title: "Some Conversations Were Dropped" ("A Conversation Was Dropped" for one).
- One paragraph: "2 of 20 planned conversations were dropped when Kiln checked them against your
  OpenEnv server. Continue reviewing the conversations that fit, or refine the plan and generate
  again." (Singular: "1 of 20 planned conversations was dropped when Kiln checked it…")
- A count only, for v1: the dropped scenarios and their reasons aren't listed. Refine Plan still
  hands them to the planner.
- Buttons: **Refine Plan** (grey) and **Continue** (primary).
  - **Refine Plan** goes back to the plan screen and opens the Refine Plan dialog there, with the
    plan's steer filled in. Its warning reads "Refining the plan discards your 18 generated
    conversations and any review progress. Every item in the new plan gets a new simulated user
    and is checked against your OpenEnv server again. This cannot be undone." Submitting plans the
    batch again with the dropped scenarios and their reasons added to the planner guidance, then
    stops on the new plan for approval. Closing the dialog leaves the plan and its results, with
    Continue back to the review.
  - **Continue** closes the dialog and leaves the review as it is.
- Any close (either button, Esc, the X) marks the notice seen. It doesn't show again for the same
  grounded cases, including after a reload or a re-drive that reuses them.

### Every case dropped

Nothing is driven, and Step 4 stays put, in the layout of its existing error screen:

- Title: "Error Creating Eval Dataset".
- Message: "None of the 20 planned conversations fit your OpenEnv server. Each row says why."
  (One planned conversation: "The planned conversation didn't fit your OpenEnv server. The row
  below says why.")
- The same dropped-cases list.
- Buttons: **Back to Plan** and **Refine Plan** (primary), which opens the Refine Plan dialog with
  the drops, as above.

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
