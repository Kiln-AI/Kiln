// Source assertions for the builder's wizard surfaces. The builder page is far
// too large to mount, but the strings and the wiring below are contractual: the
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

// Mentions of a symbol as a whole word — so counting TURNS_PER_CASE isn't
// inflated by MIN_TURNS_PER_CASE / MAX_TURNS_PER_CASE.
function whole_word_mentions(symbol: string): number {
  const pattern = new RegExp(`(?<![A-Za-z0-9_])${symbol}(?![A-Za-z0-9_])`, "g")
  return (page_source.match(pattern) ?? []).length
}

const describe_step = region(
  '{:else if current_step === "describe"}',
  '{:else if current_step === "clarify"}',
)
const plan_surface = region("<KilnProBatchPlan", "/>")
const new_plan_dialog = region("bind:this={new_plan_dialog}", "</Dialog>")
const drive_settings_dialog = region(
  "bind:this={drive_settings_dialog}",
  "</Dialog>",
)

// The Generation Settings dialog's single-turn input-generator lane.
function input_gen_lane(): string {
  const start = drive_settings_dialog.indexOf("<RunConfigComponent")
  if (start < 0) throw new Error("input generator lane not found")
  return normalize(
    drive_settings_dialog.slice(
      start,
      drive_settings_dialog.indexOf("/>", start),
    ),
  )
}

describe("describe step action row", () => {
  it("offers one forward action, with no Cancel beside it", () => {
    // Leaving the wizard is the browser's Back. A Cancel button beside the
    // primary made the row read as a two-way choice.
    expect(describe_step).not.toContain(">Cancel<")
    expect(describe_step).not.toContain("Cancel</button")
  })

  it("names the forward action Continue, like every other step", () => {
    expect(normalize(describe_step)).toContain(
      "on:click={continue_from_describe} disabled={!description.trim()} > Continue",
    )
  })

  it("demotes the manual path to the secondary-action row", () => {
    expect(normalize(describe_step)).toContain(
      'class="link underline text-sm text-gray-500" on:click={create_manually} > Create Manually',
    )
  })
})

describe("plan surface copy", () => {
  it("names the plan surface for the eval dataset it proposes", () => {
    // The header is the one label this surface overrides: what it lists is a
    // proposed eval dataset, not the synthetic data flow's batch. The
    // regenerate button keeps the shared default, so no override there.
    expect(normalize(plan_surface)).toContain(
      'header_label="Eval Dataset Proposal"',
    )
    expect(plan_surface).not.toContain("regenerate_label=")
  })

  it("renders the multi-turn subheader", () => {
    expect(
      contains(
        "Here's the plan for your eval dataset. Kiln will run each item as a test conversation with your agent in the next step. Refine the plan if the coverage looks off.",
      ),
    ).toBe(true)
  })

  it("renders the single-turn subheader", () => {
    expect(
      contains(
        "Here's the plan for your eval dataset. Kiln will use this guidance to generate each item in the next step. Refine the plan if the coverage looks off.",
      ),
    ).toBe(true)
  })

  it("labels the primary button with the artifact noun and the count", () => {
    expect(
      contains(
        "generate_button_label={`Generate Dataset (${batch_plan.prompts.length} items)`}",
      ),
    ).toBe(true)
  })

  it("names the plan's rows items and drops the /generate sub-line", () => {
    // One noun prop, so the header reads "All Items (n)" and a screen reader
    // hears "items" too. The /generate sentence is about dataset samples, which
    // is not what this surface's rows become.
    expect(normalize(plan_surface)).toContain('items_label="Items"')
    expect(normalize(plan_surface)).toContain("expanded_description={false}")
  })

  it("names the rows' column for what this surface's rows hold", () => {
    // The shared table's default header is "Prompt", which is right for
    // /generate's generation prompts. These rows are per-item guidance, so
    // this surface must override it; losing the override silently mislabels
    // the column.
    expect(normalize(plan_surface)).toContain('column_label="Item Guidance"')
  })
})

describe("plan drafting screen", () => {
  const planning_copy = region(
    "$: generate_animation_title =",
    "$: generate_animation_warning =",
  )

  it("names what is being planned, with no arm-specific noun", () => {
    expect(planning_copy).toContain(`? "Planning Eval Dataset"`)
    expect(planning_copy).not.toContain("Drafting Scenarios")
    expect(planning_copy).not.toContain("Planning Test Inputs")
  })

  it("describes the batch with each arm's artifact noun and no count", () => {
    // The count is deliberately absent: the planner can return fewer lines
    // than asked for, so quoting the request here would promise a size the
    // plan screen then contradicts.
    expect(
      contains(
        '"Kiln is planning a diverse batch of conversations, tailored to your task and guidance."',
      ),
    ).toBe(true)
    expect(
      contains(
        '"Kiln is planning a diverse batch of eval data, tailored to your task and guidance."',
      ),
    ).toBe(true)
    expect(planning_copy).not.toContain("${eval_input_count}")
  })
})

// Drops both comment forms — Svelte markup comments and script line comments —
// so the vocabulary scan below reads only what ships. The `://` guard keeps a
// URL inside an attribute value from being mistaken for a comment, which would
// truncate that attribute mid-string.
function strip_comments(source: string): string {
  return source.replace(/<!--[\s\S]*?-->/g, "").replace(/(?<!:)\/\/.*$/gm, "")
}

// Every quoted span in the source. Run against whitespace-normalized text, so a
// string Prettier wrapped across lines is still read as one string.
const QUOTED_STRING = /"[^"]*"|'[^']*'|`[^`]*`/g

describe("ruled vocabulary", () => {
  it("leaves no user-facing scenario wording on the page", () => {
    // Rows are "items" and the artifact is "traces" / "eval data". Comments
    // may still say scenario (it is the planner's own term); a shipped string
    // may not.
    const shipped = normalize(strip_comments(page_source))
    const offenders = (shipped.match(QUOTED_STRING) ?? []).filter((s) =>
      /scenario/i.test(s),
    )
    expect(offenders).toEqual([])
  })

  it("uses one word for the plan's rows on both arms", () => {
    expect(contains('const plan_noun = "items"')).toBe(true)
  })

  it("sends both arms back to the same plan screen", () => {
    expect(page_source).not.toContain("Back to Scenarios")
    // One label for both arms, matching the plan surface it leads to.
    expect(contains("Plan Batch")).toBe(true)
    expect(page_source).not.toContain("Plan Traces")
    expect(page_source).not.toContain("Plan Test Inputs")
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
    const submit = function_body("async function submit_drive_settings() {")
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
    // The committed value reaches the drive only through the clamped alias, so
    // what runs, what is stamped, and what the progress bar counts cannot
    // drift apart or fall outside the range the route accepts.
    expect(
      contains(
        "$: drive_turns_per_case = clamp_turns_per_case(turns_per_case)",
      ),
    ).toBe(true)
    // TURNS_PER_CASE is read as a DEFAULT only: its definition, the knob's
    // seed, and the restore fallback. A fourth reader would be a drive value
    // that ignores the user's choice.
    expect(whole_word_mentions("TURNS_PER_CASE")).toBe(3)
    expect(contains("const TURNS_PER_CASE = 5")).toBe(true)
    expect(contains("let turns_per_case = TURNS_PER_CASE")).toBe(true)
  })
})

describe("the turns knob", () => {
  // The multi-turn half of the dialog's arm branch: the lane and the turns row
  // that only exist when there are conversations to run.
  const multi_turn_branch = (() => {
    const start = drive_settings_dialog.indexOf("{#if is_multi_turn}")
    const end = drive_settings_dialog.indexOf("{:else}", start)
    if (start < 0 || end < 0) {
      throw new Error("the drive dialog's arm branch was not found")
    }
    return drive_settings_dialog.slice(start, end)
  })()
  // The single-turn half of the same branch, so the negatives below are about
  // THIS dialog's other arm rather than the whole page.
  const single_turn_branch = (() => {
    const start = drive_settings_dialog.indexOf("{:else}")
    const end = drive_settings_dialog.indexOf("{/if}", start)
    if (start < 0 || end < 0) {
      throw new Error("the drive dialog's single-turn arm was not found")
    }
    return drive_settings_dialog.slice(start, end)
  })()
  // The multi-turn save block, from its own guard to the request it sends.
  const multi_turn_save = region(
    "if (multi_turn_batch_tag === null || driven_cases.length === 0) {",
    "signal: new_copilot_abort_signal(),",
  )

  it("renders the stepper row only on the multi-turn arm", () => {
    // A single-turn run is one shot per input — a length control there would
    // be a knob that changes nothing.
    expect(multi_turn_branch).toContain("Max turns per conversation")
    expect(single_turn_branch).not.toContain("Max turns per conversation")
    expect(single_turn_branch).not.toContain("<IncrementUi")
  })

  it("labels the row and pins its explanation as a tooltip", () => {
    expect(normalize(multi_turn_branch)).toContain(
      "<span>Max turns per conversation</span>",
    )
    expect(normalize(multi_turn_branch)).toContain("font-medium text-sm")
    expect(
      contains(
        'tooltip_text="One turn is one exchange: the user sends a message and your agent replies. A conversation stops early once the simulated user has what it came for, so this is a ceiling rather than a target. A higher ceiling tests deeper behavior and costs more."',
      ),
    ).toBe(true)
  })

  it("binds the stepper to the STAGED knob, bounded by the route's own range", () => {
    // Staged like the dialog's model lanes: the stepper never writes the
    // committed value directly, so leaving without submitting discards it.
    const stepper = normalize(
      multi_turn_branch.slice(multi_turn_branch.indexOf("<IncrementUi")),
    )
    expect(stepper).toContain("bind:value={staged_turns_per_case}")
    expect(stepper).not.toContain("bind:value={turns_per_case}")
    expect(stepper).toContain("min={MIN_TURNS_PER_CASE}")
    expect(stepper).toContain("max={MAX_TURNS_PER_CASE}")
  })

  it("discards a nudge when the dialog closes without submitting", () => {
    // Esc / X / backdrop leave the committed value alone; the next open
    // reseeds the staged copy from it. Without this reseed a cancelled nudge
    // would survive into the next drive — and silently disqualify a top-off,
    // which refuses to mix conversation lengths.
    const open = function_body("async function open_drive_settings() {")
    expect(open).toContain("staged_turns_per_case = turns_per_case")
  })

  it("commits the staged length on submit, clamped, before driving", () => {
    const submit = function_body("async function submit_drive_settings() {")
    const commit = submit.indexOf(
      "turns_per_case = clamp_turns_per_case(staged_turns_per_case)",
    )
    expect(commit).toBeGreaterThan(-1)
    expect(commit).toBeLessThan(submit.indexOf("on_drive_multi_turn()"))
    // The clamped alias is a reactive derivation, so it still holds the
    // pre-submit length during the synchronous handler — the drive has to
    // start after the commit has landed, or it runs the old number.
    const settle = submit.indexOf("await tick()")
    expect(settle).toBeGreaterThan(commit)
    expect(settle).toBeLessThan(submit.indexOf("on_drive_multi_turn()"))
  })

  it("puts the cost warning after the row, and quotes the staged length", () => {
    // Same form, and the warning reads the clamp of the STAGED value — moving
    // the stepper re-quotes the run before the user spends on it, even though
    // nothing is committed until submit.
    const dialog = normalize(drive_settings_dialog)
    expect(dialog.indexOf("Max turns per conversation")).toBeLessThan(
      dialog.indexOf("warning_message={drive_cost_message}"),
    )
    expect(contains("turns_per_case: staged_drive_turns_per_case,")).toBe(true)
    expect(
      contains(
        "$: staged_drive_turns_per_case = clamp_turns_per_case(staged_turns_per_case)",
      ),
    ).toBe(true)
  })

  it("sends one length per drive, read once at the top", () => {
    // Read once into a local, so a stepper moved mid-drive can't change what
    // the request, the top-off decision, and the stamp are talking about.
    const drive = function_body("async function on_drive_multi_turn() {")
    expect(drive).toContain("const chosen_turns = drive_turns_per_case")
    expect(drive).toContain("turns: chosen_turns,")
    expect(drive).not.toContain("turns: drive_turns_per_case,")
  })

  it("captures the driven length beside the synthetic-user model", () => {
    // Same capture/rollback pattern as driven_su_driver: stamped at batch
    // commit, restored when nothing drove so the previous batch's stamp
    // survives a failed re-drive.
    const drive = function_body("async function on_drive_multi_turn() {")
    expect(drive).toContain(
      "const previous_driven_turns_per_case = driven_turns_per_case",
    )
    expect(drive).toContain("driven_turns_per_case = chosen_turns")
    expect(drive).toContain(
      "driven_turns_per_case = previous_driven_turns_per_case",
    )
  })

  it("refuses a top-off that would mix conversation lengths", () => {
    const drive = function_body("async function on_drive_multi_turn() {")
    const guard = drive.slice(drive.indexOf("drive_lanes_unchanged({"))
    expect(normalize(guard)).toContain("turns: chosen_turns,")
    expect(normalize(guard)).toContain("batch_turns: driven_turns_per_case,")
  })

  it("stamps the driven length on save, never the live knob", () => {
    // The stepper can move after the drive; the saved eval must describe the
    // conversations that exist on disk. Save fails loud rather than guessing a
    // length for chains it has no record of.
    expect(multi_turn_save).toContain(
      "const saved_turns_per_case = driven_turns_per_case",
    )
    expect(multi_turn_save).toContain(
      "No conversation length was recorded for the driven conversations. Go back to Step 4.",
    )
    expect(normalize(multi_turn_save)).toContain("turns: saved_turns_per_case,")
    expect(multi_turn_save).not.toContain("drive_turns_per_case")
  })

  it("counts progress against the driven length", () => {
    // A stepper moved while the bar is on screen must not restate the
    // denominator under a batch already running at another length.
    expect(
      contains(
        "$: multi_turn_total_turns = pipeline_total_cases * (driven_turns_per_case ?? drive_turns_per_case)",
      ),
    ).toBe(true)
  })

  it("persists the chosen length and restores it through the clamp", () => {
    // The mirror is what puts the choice on disk; without it a reload silently
    // puts the drive back on the default. A stored value can predate today's
    // range, and a draft written before the knob existed carries no value.
    const mirror = region("$: current_draft = draft_ready", "    : null")
    expect(normalize(mirror)).toContain("turns_per_case,")
    const restore = normalize(function_body("async function restore_draft() {"))
    expect(restore).toContain(
      "turns_per_case = restore_turns_per_case( saved.turns_per_case, TURNS_PER_CASE, )",
    )
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
      contains("submit_label={`Generate Dataset (${planned_total} items)`}"),
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
        'model_info_description="Writes one item from each approved plan line; your task then runs on them."',
      ),
    ).toBe(true)
    expect(contains('model_label="Eval Data Generation Model"')).toBe(true)
  })

  it("gives the input generator the same control synthetic data generation uses", () => {
    // Tools and skills change what the eval data looks like, so this lane is
    // the full run config picker rather than a bare model dropdown.
    const lane = input_gen_lane()
    expect(lane).toContain("hide_prompt_selector={true}")
    expect(lane).toContain("show_tools_selector_in_advanced={true}")
    expect(lane).toContain("show_name_field={false}")
  })

  it("gives the lane no task, so its tools stay out of the app-wide store", () => {
    // The tool and skill pickers seed from, and mirror every change into,
    // tools_store keyed by task id — a parent's write counts the same as a
    // user's click. With no task they skip that store entirely and are still
    // fully populated from the project. Passing a task here would let this
    // dialog's tools overwrite the ones chosen on Run and Synthetic Data, and
    // let those overwrite a restored draft's.
    const lane = input_gen_lane()
    expect(lane).not.toContain("current_task")
    expect(lane).not.toContain("bind:tools")
    expect(lane).not.toContain("bind:skills")
  })

  it("seeds the lane from the config it last committed", () => {
    // The component stays mounted between opens, so both a restored draft and
    // a visit abandoned by Cancel have to be seeded back to the committed
    // config rather than left showing stale edits.
    expect(input_gen_lane()).toContain(
      "initial_run_config_properties={input_gen_run_config}",
    )
    const open = normalize(
      function_body("async function open_drive_settings() {"),
    )
    expect(open).toContain(
      "input_gen_config_component?.apply_run_config_properties( input_gen_run_config, )",
    )
    // Nothing committed yet still has to reseed: the lane goes back to the
    // defaults a first open shows, or an abandoned visit's edits survive it.
    expect(open).toContain("input_gen_config_component?.reset_run_options()")
  })

  it("carries the committed config on the draft so a reload can still run", () => {
    // Without it a restored session would be bounced back into the dialog
    // before it could drive.
    const mirror = region("$: current_draft = draft_ready", "    : null")
    expect(normalize(mirror)).toContain("input_gen_run_config,")
    expect(
      normalize(function_body("async function restore_draft() {")),
    ).toContain("input_gen_run_config = saved.input_gen_run_config ?? null")
  })

  it("sends the committed run config to the minting route, not a rebuilt one", () => {
    // Tools and skills only reach the generator if the whole config the user
    // configured is what gets sent.
    const mint = normalize(
      function_body("async function mint_inputs_from_plan("),
    )
    expect(mint).toContain("run_config_properties: input_gen_config,")
    expect(mint).not.toContain('prompt_id: "simple_prompt_builder"')
  })

  it("keys the minted-inputs cache on the config it sends", () => {
    // Sampling and tools are both editable in this lane and both change what
    // is written, so the key is the whole config, derived from the very
    // object the request carries.
    const drive = normalize(
      function_body("async function on_drive_single_turn() {"),
    )
    expect(drive).toContain(
      "const input_gen_config_key = run_config_cache_key(chosen_input_config)",
    )
    expect(drive).toContain("run_config_json: input_gen_config_key,")
  })

  it("names the judge lane once and explains it per arm", () => {
    expect(contains('label="Judge Model"')).toBe(true)
    expect(
      contains(`"Checks each conversation against your eval's criteria."`),
    ).toBe(true)
    expect(contains(`"Checks each result against your eval's criteria."`)).toBe(
      true,
    )
  })

  it("quiets the suggested-model advisory on the model-only lanes", () => {
    // Lanes stacked in one dialog, each confirming a good default, is a wall
    // of green checks. The flag drops only that confirmation; a lane on a
    // model we don't suggest still says so. The input generator keeps the
    // advisory, matching the same control in synthetic data generation.
    const lanes = drive_settings_dialog
      .split("<AvailableModelsDropdown")
      .slice(1)
      // Bound each chunk at its own tag close, or a flag on the last lane would
      // satisfy the assertion for every earlier one.
      .map((chunk) => chunk.slice(0, chunk.indexOf("/>")))
    expect(lanes.length).toBe(2)
    for (const lane of lanes) {
      expect(normalize(lane)).toContain("quiet_suggested={true}")
    }
    expect(input_gen_lane()).not.toContain("quiet_suggested")
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

describe("Refine Plan dialog", () => {
  it("replaces the native confirm on the regenerate button", () => {
    expect(normalize(plan_surface)).toContain(
      "on_regenerate={open_new_plan_dialog}",
    )
    expect(mentions("on_new_plan_with_confirm")).toBe(0)
  })

  it("names the action it performs, never the drive's verb", () => {
    // This dialog only re-plans — it generates nothing — so neither label may
    // borrow the drive's verb. The title says which plan it replaces; the
    // submit still echoes the shared regenerate button that opens it.
    expect(normalize(new_plan_dialog)).toContain('title="New Dataset Plan"')
    expect(normalize(new_plan_dialog)).toContain('submit_label="Refine Plan"')
    expect(new_plan_dialog).not.toContain("Generate Batch")
    expect(new_plan_dialog).not.toContain("Generate Trace Batch")
    expect(new_plan_dialog).not.toContain("Generate Dataset")
  })

  it("wraps the shared batch form with the ruled count label", () => {
    expect(normalize(new_plan_dialog)).toContain('count_label="Item Count"')
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

  it("marks the guidance box optional so a blank steer submits", () => {
    // The box starts empty on purpose, so the default "just re-plan" click
    // sends nothing. Without this the shared field's required-validator
    // rejects the empty box and the regenerate path can never run.
    expect(normalize(new_plan_dialog)).toContain("guidance_optional={true}")
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
