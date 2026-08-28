// Source assertions for Step 4's generate surface. The builder page is far too
// large to mount, but the strings and the wiring below are contractual: the
// ruled copy, and the rule that the Generation Settings dialog is the drive's
// ONLY entrance. Reading the source is the house precedent for pinning facts a
// render test can't reach (see lib/agent_coverage.test.ts).
import { describe, expect, it } from "vitest"
import * as fs from "fs"
import * as path from "path"

const page_source = fs.readFileSync(
  path.resolve(__dirname, "./+page.svelte"),
  "utf-8",
)

// Collapses runs of whitespace so an assertion survives Prettier rewrapping a
// long attribute across lines.
function normalize(source: string): string {
  return source.replace(/\s+/g, " ")
}

const normalized = normalize(page_source)

function contains(needle: string): boolean {
  return normalized.includes(normalize(needle))
}

// The slice of the page a claim is actually about. Negative assertions run
// against a region rather than the whole 4900-line file: "Advanced Settings"
// appearing on some unrelated future surface is not a regression of the drive
// dialog's title, and a whole-file not.toContain would say it was.
function region(start_anchor: string, end_anchor: string): string {
  const start = page_source.indexOf(start_anchor)
  if (start < 0) {
    throw new Error(`anchor not found in +page.svelte: ${start_anchor}`)
  }
  const end = page_source.indexOf(end_anchor, start + start_anchor.length)
  if (end < 0) {
    throw new Error(
      `end anchor not found after "${start_anchor}": ${end_anchor}`,
    )
  }
  return page_source.slice(start, end + end_anchor.length)
}

// A function body: from its signature to the closing brace at script indent.
function function_body(signature: string): string {
  return region(signature, "\n  }")
}

// How many times a symbol is named on the page — the entrance count for a
// drive function (its own definition plus its legitimate callers).
function mentions(symbol: string): number {
  return page_source.split(symbol).length - 1
}

const plan_surface = region("<KilnProBatchPlan", "/>")
const new_plan_dialog = region("bind:this={new_plan_dialog}", "</Dialog>")
const drive_settings_dialog = region(
  "bind:this={drive_settings_dialog}",
  "</Dialog>",
)

describe("plan surface copy", () => {
  it("uses the shared component's default header and regenerate labels", () => {
    // Deleted overrides, so the plan reads "Batch Plan" / "New Batch Plan" —
    // the same words the synthetic data flow already shows.
    expect(plan_surface).not.toContain("header_label=")
    expect(plan_surface).not.toContain("regenerate_label=")
  })

  it("renders the multi-turn subheader", () => {
    expect(
      contains(
        "Kiln will run each item as a test conversation with your agent. Remove any you don't want before starting.",
      ),
    ).toBe(true)
  })

  it("renders the single-turn subheader", () => {
    expect(
      contains(
        "Kiln will run your task on each item. Remove any you don't want before starting.",
      ),
    ).toBe(true)
  })

  it("labels the primary button with the artifact noun and the count", () => {
    expect(
      contains(
        "generate_button_label={`Generate Traces (${batch_plan.prompts.length})`}",
      ),
    ).toBe(true)
  })
})

describe("single entrance to the drive", () => {
  it("routes the plan's primary button into the settings dialog", () => {
    expect(normalize(plan_surface)).toContain(
      "on_generate_inputs={open_drive_settings}",
    )
  })

  it("has no run-immediately path left", () => {
    // start_drive_with_defaults was the second entrance; it is gone entirely,
    // not merely unreferenced.
    expect(mentions("start_drive_with_defaults")).toBe(0)
  })

  it("drops the advanced slot's model-choice link", () => {
    expect(normalize(plan_surface)).not.toContain('slot="advanced"')
    expect(plan_surface).not.toContain("choose which models to use")
  })

  it("starts a drive only from the settings dialog's submit", () => {
    const submit = function_body("function submit_drive_settings() {")
    expect(submit).toContain("on_drive_multi_turn()")
    expect(submit).toContain("on_drive_single_turn()")
    // Each arm's drive function is named exactly twice on the page: its own
    // definition and that submit's call. A third mention is a second
    // entrance — a run the user was never shown the lanes or the cost of.
    expect(mentions("on_drive_multi_turn")).toBe(2)
    expect(mentions("on_drive_single_turn")).toBe(2)
  })

  it("opens the dialog from the error screen's Retry", () => {
    // Retrying a failed drive is still a drive: it re-states the lanes and the
    // cost rather than re-spending on the last attempt's settings silently.
    const retry = function_body("function on_continue_from_generate_step() {")
    expect(retry).toContain("open_drive_settings()")
    expect(retry).not.toContain("on_drive_")
  })

  it("opens the dialog for the no-results re-drive", () => {
    // Advancing to review with nothing to show (a Back aborted the pipeline)
    // re-drives — through the same entrance as the first attempt.
    const advance = function_body("function continue_to_review() {")
    expect(advance).toContain("open_drive_settings()")
    expect(advance).not.toContain("on_drive_")
  })

  it("derives every turn count from the one alias", () => {
    // TURNS_PER_CASE is named twice: its definition and the alias. Every
    // reader — the cost warning, the drive request, the progress denominator,
    // the saved drive stamp — goes through drive_turns_per_case, so what the
    // user is quoted and what runs cannot drift apart.
    expect(mentions("TURNS_PER_CASE")).toBe(2)
    expect(contains("$: drive_turns_per_case = TURNS_PER_CASE")).toBe(true)
  })
})

describe("Generation Settings dialog", () => {
  it("is titled Generation Settings", () => {
    expect(
      contains(
        '<Dialog bind:this={drive_settings_dialog} title="Generation Settings">',
      ),
    ).toBe(true)
  })

  it("no longer carries the old Advanced Settings title", () => {
    expect(drive_settings_dialog).not.toContain("Advanced Settings")
  })

  it("submits with the artifact noun and the planned count", () => {
    expect(
      contains("submit_label={`Generate Traces (${planned_total})`}"),
    ).toBe(true)
  })

  it("pins each lane's explanation as a tooltip, not a visible description", () => {
    expect(
      contains(
        'info_description="Stands in for a real user in each test conversation. Your agent replies to it."',
      ),
    ).toBe(true)
    expect(contains('label="Model that writes the user\'s messages"')).toBe(
      true,
    )
    expect(
      contains(
        'info_description="Writes one test input from each approved plan line; your task then runs on them."',
      ),
    ).toBe(true)
    expect(contains('label="Model that writes the test inputs"')).toBe(true)
  })

  it("names the judge lane per arm", () => {
    expect(contains('"Model that grades each conversation"')).toBe(true)
    expect(contains('"Model that grades each result"')).toBe(true)
    expect(
      contains(
        `"Checks each conversation against your eval's criteria, then marks pass or fail."`,
      ),
    ).toBe(true)
    expect(
      contains(
        `"Checks each result against your eval's criteria, then marks pass or fail."`,
      ),
    ).toBe(true)
  })

  it("puts the cost warning immediately before the submit", () => {
    // Last child of the FormContainer = directly above the submit row, which
    // is the one button that spends the credits.
    const dialog = normalize(drive_settings_dialog)
    const warning = dialog.indexOf("warning_message={drive_cost_message}")
    const close = dialog.indexOf("</FormContainer>")
    expect(warning).toBeGreaterThan(-1)
    expect(warning).toBeLessThan(close)
    // Nothing else renders between the warning and the form's close.
    expect(dialog.slice(warning, close)).not.toContain("<AvailableModels")
  })

  it("fills the dropdowns once the lane pre-population resolves", () => {
    // The dialog shows immediately; the reseed must run AFTER the pass that
    // fills the lanes, or the dropdowns open empty on the eager-start path.
    const open = function_body("async function open_drive_settings() {")
    const show = open.indexOf("drive_settings_dialog?.show()")
    const awaited = open.indexOf("await prepopulate_lanes()")
    const reseed = open.indexOf("su_model_combined = su_driver")
    expect(show).toBeGreaterThan(-1)
    expect(awaited).toBeGreaterThan(show)
    expect(reseed).toBeGreaterThan(awaited)
    // The pass is memoized as a promise, so a second caller awaits the one in
    // flight instead of returning early while the lanes are still null.
    expect(
      contains("let lanes_prepopulated: Promise<void> | null = null"),
    ).toBe(true)
  })
})

describe("New Batch Plan dialog", () => {
  it("replaces the native confirm on the regenerate button", () => {
    expect(normalize(plan_surface)).toContain(
      "on_regenerate={open_new_plan_dialog}",
    )
    expect(mentions("on_new_plan_with_confirm")).toBe(0)
  })

  it("names the action it performs, in both the title and the submit", () => {
    // This dialog only re-plans — it generates nothing — so it echoes the
    // button that opens it rather than borrowing the drive's verb.
    expect(normalize(new_plan_dialog)).toContain('title="New Batch Plan"')
    expect(normalize(new_plan_dialog)).toContain(
      'submit_label="New Batch Plan"',
    )
    expect(new_plan_dialog).not.toContain("Generate Batch")
    expect(new_plan_dialog).not.toContain("Generate Trace Batch")
  })

  it("wraps the shared batch form with the ruled count label", () => {
    expect(normalize(new_plan_dialog)).toContain('count_label="Trace Count"')
    expect(normalize(new_plan_dialog)).toContain('guidance_id="plan_steer"')
  })

  it("caps the stepper at the server's batch cap", () => {
    // The stepper must stop where the routes reject, so the user can't compose
    // a request that can only 422.
    expect(contains("const NUM_CASES_MAX = 200")).toBe(true)
    expect(normalize(new_plan_dialog)).toContain("count_max={NUM_CASES_MAX}")
  })

  it("binds the guidance box to the steer rather than prefilling a template", () => {
    expect(normalize(new_plan_dialog)).toContain("bind:guidance={plan_steer}")
    expect(new_plan_dialog).not.toContain("guidance_template=")
  })

  it("leaves the guidance example to the shared field's own description", () => {
    // The shared Guidance field already carries an example; a second one
    // stacked under it reads as noise.
    expect(new_plan_dialog).not.toContain("guidance_placeholder")
  })

  it("discards a typed steer when the dialog closes without submitting", () => {
    // The box is a DRAFT. Only a submit copies it into the steer the request
    // sends, so a steer the user typed and then abandoned cannot ride a later
    // plan request.
    expect(normalize(new_plan_dialog)).toContain(
      "on:close={discard_plan_steer_draft}",
    )
    expect(function_body("function discard_plan_steer_draft() {")).toContain(
      "plan_steer = pending_plan_steer",
    )
    expect(function_body("function submit_new_plan() {")).toContain(
      "pending_plan_steer = plan_steer",
    )
  })

  it("sends the committed steer, never the dialog's draft", () => {
    const request = region("compose_plan_guidance(", "count: eval_input_count,")
    expect(request).toMatch(/\bpending_plan_steer\b/)
    expect(request).not.toMatch(/(?<!pending_)\bplan_steer\b/)
  })

  it("keeps the steer through a failed attempt and drops it once a plan lands", () => {
    // Retention lives in on_plan_batch's early returns: every failure path
    // returns before the clear below, so Retry re-sends what was asked for.
    const plan = function_body("async function on_plan_batch() {")
    expect(plan).toContain('pending_plan_steer = ""')
    expect(
      plan.indexOf("batch_plan = { prompts, summary: data.summary }"),
    ).toBeLessThan(plan.indexOf('pending_plan_steer = ""'))
  })

  it("reseeds the count from the last request when no plan is on screen", () => {
    // After a failed regenerate there is no plan to read the size from;
    // eval_input_count still holds what that attempt asked for, so the dialog
    // and Retry agree instead of the stepper snapping back to the default.
    const open = function_body("function open_new_plan_dialog() {")
    expect(open).toContain(
      "if (batch_plan) eval_input_count = batch_plan.prompts.length",
    )
    expect(open).not.toContain("NUM_CASES")
  })
})
