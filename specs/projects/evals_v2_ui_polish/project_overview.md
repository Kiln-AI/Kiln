---
status: complete
---

# Evals V2 — Create-Flow UI Polish

We've been working on the Evals V2 UI in this branch. This is a project to improve the UI
further. It's a set of lots of feedback.

The design spec files referenced below live in `design_specs/` (copied in from the design
agent's wireframes):

- `design_specs/select_screen.md`
- `design_specs/test_run_sidebar.md`

> **Design-agent caveat (applies throughout):** the design agent was wire-framing — it was
> not reading code and not using a Kiln style guide. Use its **layout guidance**, but do
> **visual design matching Kiln style**. For strings/content: take its strings where they're
> correct, but **verify correctness — the code is source of truth** for what each eval type
> does. Don't over-index on the design bot's design, but do take the design wins. Where the
> wireframe conflicts with code reality, ask questions during speccing.

---

## Select Eval Type screen — visual update

A design agent has made a much better design for this screen. See `design_specs/select_screen.md`
(a spec from the design agent).

Note: the design agent was wire-framing, not reading code, not using a Kiln style guide. Use
its layout guidance, but do visual design matching Kiln style. Strings/Content: take its
design strings where they are correct, but verify correctness — the code is source of truth
for what each eval type does.

---

## "Allow Code Execution" modal is ugly and broken

Update modal:

- Title: "Trust Code and Project?"
- Body line 1: "This project wants to run Python code on your machine. Only proceed if you
  trust the eval code and this project."
- Body line 2, bold: "**Never paste code from a stranger or the internet.**"
- Design: yellow box is ugly. Use our large warning icon, but not yellow BG under text.
- Buttons should be "Run — I Trust This Code" and "Cancel".

Bug:

- Trust dialog stays up after you click trust, while running. But the content clears out and
  it's an ugly empty modal. Should dismiss right away, and see a running spinner on the main
  page (doesn't exist yet, but it will).

---

## Code Judge Creation page updates

- "Score Function" header should use our standard header for a form component (there's a
  header-only option, when content is custom).
  - Make subtitle: "Define a Python score function to evaluate the model's work."
  - Add tooltip: "The python function can use the model's output, trace, and eval's
    reference data to drive pragmatic scoring. Faster and cheaper than LLM as a judge."
  - "See examples" — keep action on right of title. Might need to add support to header
    control? Update to: "More Examples".
- Remove footer: "Define a score(output, trace, reference_data, task_input, kiln) function
  that returns a dict of score names to score values. Ranges vary by type: pass/fail uses
  0.0–1.0, pass/fail/critical uses -1.0–1.0, and five-star uses 1.0–5.0."
  - Subtitle and code sample do a better job here.
- "**Code: Custom Python Code Eval**" title should be removed, but is weirdly indented. Make
  sure weird indenting is gone regardless of this specific instance.
- Test Run: sidebar needs a lot of work.
  - Outline isn't our style at all. Use our standard 2-column layout like the /run page. Same
    for column title font: make it consistent with app.
  - Needs a nice spinner state when running.
  - The control to select an output is much too complicated to inline like you have.
  - New design wireframes described in `design_specs/test_run_sidebar.md`. Some notes on
    integrating it:
    - Like above, the design agent did a wireframe, not a code-expert pass — merge its
      guidance with code reality. Ask questions in speccing for conflicts. Don't over-index
      on the design-bot's design, but do take the design wins.
    - Main screen: just shows selected option + 2 other options (design says 3, but do 3
      total, selected + 2 more). Way too much in there now.
    - Options on main screen need to be small/short/clean. Show truncated 2 lines of input
      and output, with whole strings in tooltip. Note design md only shows input, but you're
      right we need to show both. Close to current design for "Selected Run" but cleaned up
      and more to our design guide.
    - The control to browse is now in a modal. "Wide" modal. Basically the control you have
      inline now, updated in style to match our UI better, and moved into a modal where it
      has enough room to breathe.
    - Modal has "Add manual example" option, launching a new modal allowing the user to paste
      in input/output strings.
    - Design discrepancies: despite what design says: no search in modal; outputs included —
      not just inputs.
  - Select into modal.
  - Select first by default. Only ever 1 visible.
  - Manual/custom option missing, add to modal.
- Reference Data UI update.
  - Show "Reference Data: None"-style control. Clicking None/content brings up a text editor
    in a modal. Use our standard form look, updated to this style.
- No spinners while running, needs one.

---

## LLM as Judge integration

- The "cards" here are too big given the new column on the right. Shrink them by 40%, and
  update design to work (smaller icons).

---

## Layout

- Titles need work. Every page is "**Add a Judge**" but then has a salient subtitle like
  "**Code: Custom Python Code Eval**".
  - Titles and subtitles should be better per page, not all generic. Example:
    - Title: "Add a Code Judge"
    - Subtitle: "Write a Python function that scores model outputs."
    - No secondary title section underneath.
  - Similarly for "Add a Judge" + "**Select Eval Type**" → "Add Judge: Select Judge Type".

---

## Misc Bugs

- If I hit the "Save" button on the code screen before testing, then cancel in the "Save
  Without Testing?" modal, the save button is left spinning on the main screen. Now the user
  is stuck.
- Audit "read the docs" links: many are no good! Remove them unless they really link to a
  1) real link, 2) link salient to topic (e.g., code judges).

---

## Polish on other screens

Each of the other create screens needs a more thoughtful UI/UX design.

Create a phase for 1) general cleanup of the container (shared "what" section, better shared
UI), and 2) per-screen polish.

Use Claude's `/frontend_design` skill.

Some concerns just from looking at "Exact Match":

- Does the user understand labels? Are they designed with UI best practices in mind?
  - Example:
    - "Value Expression" — "Optional Jinja2 expression to extract a value from the eval
      input before comparison. Leave blank to use the full model output."
    - Critique: what the hell does that mean??
      - "Output Value to Compare"
      - "Leave blank to compare the entire model output, or use a Jinja expression like
        `user.email` to extract fields from JSON in the output."
      - Tooltip: explain what Jinja is.
  - Generally these are all weak. We want:
    - Better names
    - Better subtitles
    - More tooltips
- Missing context: "Exact Match" evals are described better on the "**Select Eval Type**"
  screen than on the Exact Match screen.
  - We should explain what the eval type is at the top in an info section. Clear "what", and
    when needed, examples.
- No radio buttons: we rarely use radios, you've got nested radios where entire UI sections
  stop working.
  - Progressive disclosure: choose "Fixed Value vs Value from Reference Data" first, then ask
    the follow-up question related to that.
  - Add section titles. Exact Match could have 2: "Expected Value" and "Output Value to
    Compare". Can relate back up to the examples/header where we explain how this eval type
    works.
- Anything else: nothing in this UI was specced / is locked / has been reviewed. Make them
  better when you discover a UI/UX issue.
- Consistent to Kiln design guide: see our form design info.
