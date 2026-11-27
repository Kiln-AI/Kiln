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
const plan_surface = region("<KilnProBatchPlan", "</KilnProBatchPlan>")
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
    // proposed eval dataset, not the synthetic data flow's batch.
    expect(normalize(plan_surface)).toContain(
      'header_label="Eval Dataset Proposal"',
    )
  })

  it("renders one subheader, the same on both arms", () => {
    // What the next step does to each row belongs on that step, not in the
    // plan's sub-line: one sentence reads the same whether the run drives
    // conversations or generates single inputs.
    expect(normalize(plan_surface)).toContain(
      'subheader="Here\'s a plan for your eval dataset. Refine the plan if the coverage looks off."',
    )
    expect(plan_surface).not.toContain("is_multi_turn")
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
    expect(normalize(plan_surface)).toContain(
      'expanded_description="Each row will be used to seed one item of your eval dataset."',
    )
  })

  it("puts the data guide note on the sub-line, only when a guide was used", () => {
    // The note is a clause on the header's sub-line rather than a row of its
    // own, so the plan surface opens with one sentence. It is a claim about
    // how the plan was drafted, so it renders only when that is true.
    const normalized_surface = normalize(plan_surface)
    expect(normalized_surface).toContain(
      '<svelte:fragment slot="under_subheader"> {#if plan_drafted_with_data_guide}',
    )
    // The clause, normalized so Prettier's wrapping is not what is pinned. It
    // has to open with an explicit space, because Svelte drops whitespace at
    // the start of slot content and the sub-line adds no separator of its own.
    const note = normalize(region('<span id="data_guide_plan_note"', "</span"))
    expect(note).toContain('{" "}Planned using your')
    expect(note).toContain("data guide</button")
    expect(note.endsWith(".</span")).toBe(true)
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
    expect(planning_copy).not.toContain("planned_count(")
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
    // Each arm's drive function is named only by its own definition and that
    // submit's call. Any other mention is a second entrance — a run the user
    // was never shown the lanes or the cost of.
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
    const end = drive_settings_dialog.indexOf(
      "{:else if !grounds_single_turn}",
      start,
    )
    if (start < 0 || end < 0) {
      throw new Error("the drive dialog's arm branch was not found")
    }
    return drive_settings_dialog.slice(start, end)
  })()
  // The single-turn half of the same branch, so the negatives below are about
  // THIS dialog's other arm rather than the whole page.
  const single_turn_branch = (() => {
    const start = drive_settings_dialog.indexOf(
      "{:else if !grounds_single_turn}",
    )
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
    const open = function_body("async function open_drive_settings(")
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
    expect(contains('label="Synthetic User Model"')).toBe(true)
    expect(
      contains(
        'model_info_description="Writes the input for each dataset item. Your run config then produces the output that the judge scores."',
      ),
    ).toBe(true)
    // The lane writes the input half of each dataset item; the output comes
    // from the run config the eval is about, so the label says which of the
    // two this model is.
    expect(contains('model_label="Input Generation Model"')).toBe(true)
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
    const open = normalize(function_body("async function open_drive_settings("))
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

  it("recommends the user-model lane's own tier, and filters on nothing", () => {
    // The simulated user writes one plain-text message a turn: no schema, no
    // tools. Recommending it from the data-gen flag pointed at the frontier
    // models, and requiring data-gen support pushed usable chat models into
    // "Not Recommended". It now reads its own registry flag and excludes
    // nothing.
    const su_lane = drive_settings_dialog.slice(
      drive_settings_dialog.indexOf("<AvailableModelsDropdown"),
    )
    const lane = normalize(su_lane.slice(0, su_lane.indexOf("/>")))
    expect(lane).toContain('suggested_mode: "synthetic_user"')
    expect(lane).not.toContain("requires_")
    // The lane's pre-selected default comes from the same set that badges it,
    // so the dialog does not open on a model its own advisory warns about.
    expect(
      normalize(function_body("async function fill_null_lanes() {")),
    ).toContain('build_suggested_models(models, "synthetic_user")[0]')
  })

  it("names the judge lane once and explains it per arm", () => {
    expect(contains('label="Judge Model"')).toBe(true)
    expect(contains(`"Grades each conversation against your eval."`)).toBe(true)
    expect(contains(`"Grades each result against your eval."`)).toBe(true)
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

  it("seeds every lane before the dialog is shown", () => {
    // Order is the whole fix: showing first let the user pick a model while
    // the defaults were still resolving, and the reseed then overwrote it.
    // Pinned by index, because only the sequence is wrong in the old version.
    const open = function_body("async function open_drive_settings(")
    const awaited = open.indexOf("await prepopulate_lanes()")
    const reseed = open.indexOf("judge_model_combined = judge_model")
    const show = open.indexOf("drive_settings_dialog?.show()")
    expect(awaited).toBeGreaterThan(-1)
    expect(reseed).toBeGreaterThan(awaited)
    expect(show).toBeGreaterThan(reseed)
    // The pass is memoized as a promise, so a second caller awaits the one in
    // flight instead of returning early while the lanes are still null.
    expect(
      contains("let lanes_prepopulated: Promise<void> | null = null"),
    ).toBe(true)
    // A failed pass must still open the dialog on whatever is committed,
    // rather than swallow the click.
    expect(open).toContain('console.warn("Could not resolve the default')
  })

  it("clears a stale validation error when a lane changes", () => {
    // The error names a condition ("… to continue"); once the user fills the
    // lanes the condition is gone, so the sentence must go with it instead of
    // standing over two filled dropdowns. All four editable values are
    // dependencies, and the error itself is not read — raising it in submit
    // must not immediately re-run the clear.
    const statement = region(
      "$: drive_settings_error = cleared_on_lane_change(",
      ")",
    )
    const dependencies = normalize(
      statement.slice(statement.indexOf("(") + 1, statement.lastIndexOf(")")),
    )
    expect(dependencies).toContain("su_model_combined")
    expect(dependencies).toContain("input_gen_model_combined")
    expect(dependencies).toContain("judge_model_combined")
    expect(dependencies).toContain("staged_turns_per_case")
    expect(dependencies).not.toContain("drive_settings_error")
    expect(
      normalize(function_body("function cleared_on_lane_change(")),
    ).toContain("return null")
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

  it("asks for the size above the shared batch form's rows", () => {
    // Size first, then the steer: the order the dialog reads in, and the
    // reason the picker is a sibling of the form rather than inside it.
    expect(normalize(new_plan_dialog)).toContain(
      "<BatchSizePicker bind:size={staged_batch_size} /> <KilnProBatchForm",
    )
    expect(normalize(new_plan_dialog)).toContain('guidance_id="plan_steer"')
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
    // Both arms' guidance is built in plan_guidance.
    const request = function_body("async function plan_guidance(")
    expect(request).toMatch(/\bpending_plan_steer\b/)
    expect(request).not.toMatch(/(?<!pending_)\bplan_steer\b/)
  })

  it("keeps the steer through a failed attempt and drops it once a plan lands", () => {
    // Retention lives in on_plan_batch's early returns: every failure path
    // returns before the clear below, so Retry re-sends what was asked for.
    const plan = function_body("async function on_plan_batch() {")
    expect(plan).toContain('pending_plan_steer = ""')
    expect(plan.indexOf("batch_plan = planned")).toBeLessThan(
      plan.indexOf('pending_plan_steer = ""'),
    )
  })

  it("discards a picked size when the dialog closes without submitting", () => {
    // The picker is a DRAFT, like the steer beside it: the size that plans and
    // that the save deals by only changes on a submit.
    expect(function_body("function open_new_plan_dialog() {")).toContain(
      "staged_batch_size = { ...batch_size }",
    )
    expect(function_body("function discard_plan_steer_draft() {")).toContain(
      "staged_batch_size = { ...batch_size }",
    )
    expect(function_body("function submit_new_plan() {")).toContain(
      "batch_size = { ...staged_batch_size }",
    )
  })

  it("deals the save by the size the user chose", () => {
    // Both arms build the same eval shape, so neither may pin its own splits.
    expect(mentions("splits: shares_for(batch_size),")).toBe(2)
  })
})

describe("Data Guide skip and Back", () => {
  // Back out of an unplanned Step 4 must re-offer, as it does on the
  // synthetic data page; the reset lives in the history handler.
  const handler = region(
    "function sync_step_from_history",
    "current_step = step",
  )

  it("clears the skip when Back leaves Step 4 without a plan", () => {
    expect(normalize(handler)).toContain(
      normalize(
        'if (current_step === "generate" && batch_plan === null) { data_guide_skipped = false }',
      ),
    )
  })
})

describe("Reset", () => {
  const reset = region("async function reset_draft_with_confirm", "\n  }\n")

  it("starts over on the Create Eval page, not by reloading a URL that may carry a description", () => {
    expect(normalize(reset)).toContain(
      normalize(
        "window.location.href = `/specs/${project_id}/${task_id}/select_template`",
      ),
    )
    expect(reset).not.toContain("window.location.reload()")
  })
})

describe("the run config the eval is written against", () => {
  // The signature's own return type closes at script indent, so the shared
  // function_body helper would stop there; take the whole function instead.
  const resolve = region(
    "async function resolve_drive_run_config(",
    "// ── Step 4 — both arms are plan-first over one pipeline shape.",
  )

  it("drives the config the entry page chose over the task default", () => {
    // The questions, the judge and the generated data were all authored
    // against that config, so driving the task default instead would produce
    // eval data for a different agent than the one the eval describes. The
    // order itself is pick_target_run_config's, tested in plan_flow.test.ts.
    const body = normalize(resolve)
    expect(body).toContain(
      "const picked = pick_target_run_config( run_configs, target_run_config_id, task.default_run_config_id, )",
    )
    // The no-default notice names a config the user did not pick. An explicit
    // choice is not a fallback, so it must not raise it.
    expect(body).toContain(
      "fallback_run_config_name = picked.is_fallback ? chosen_config.name : null",
    )
  })

  it("stops the drive when the chosen config is no longer on the task", () => {
    // Driving the task default instead would generate eval data for an agent
    // this eval does not describe, and say nothing about it.
    const body = normalize(resolve)
    expect(body).toContain(
      'if (!picked) { generation_error = "The run config this eval was written against is no longer on the task.',
    )
    expect(body).toContain("return null")
  })

  it("keeps the choice across a reload", () => {
    expect(
      normalize(region("$: current_draft = draft_ready", "    : null")),
    ).toContain("target_run_config_id,")
    expect(
      normalize(function_body("async function restore_draft() {")),
    ).toContain("target_run_config_id = saved.target_run_config_id ?? null")
  })

  it("tells the copilot calls that read a config which one to read", () => {
    // Server-side these calls read the config's tools and skills; without the
    // id they read the task default and describe the wrong agent. Only the
    // calls that read capabilities are wired — the save reads none, so
    // sending it there would be a field the server accepts and discards.
    expect(mentions("run_config_id: target_run_config_id")).toBe(2)
    expect(
      normalize(
        region("async function on_save() {", "function create_manually()"),
      ),
    ).not.toContain("run_config_id")
  })
})

// ── The review-preparation and drive progress screens ──────────────────────
//
// Every waiting screen on this step reads the same way: a static title and
// description, and one ProgressCount under the bar carrying every live number.
// A count inside a sentence re-lays that sentence out on every tick; under the
// bar it changes in place. These pin where each count lives, because the
// difference is invisible to a render test that only reads text.
describe("progress screens carry their counts under the bar, never in a string", () => {
  it("leaves the claims gate's title static on both the first round and a later one", () => {
    // Once for the first-round gate, once for the calibration round's.
    expect(normalized.split('title="Preparing Review"').length - 1).toBe(2)
    expect(normalized).toContain(
      'description="Finding the examples where your judgment is most useful."',
    )
    // The count it used to carry now sits under that screen's bar.
    expect(normalized.split("noun={`${judged_noun}s ready`}").length - 1).toBe(
      2,
    )
  })

  it("leaves the drive descriptions static, with the counts under the bar", () => {
    expect(normalized).toContain(
      'description="Simulating conversations with your agent and judging each one."',
    )
    expect(normalized).toContain(
      'description="Running your task on each item and judging the result."',
    )
    expect(normalized).toContain('noun="turns complete"')
    expect(normalized).toContain('noun="judged"')
    // No screen hand-rolls a bar any more: they all go through the component,
    // so the readouts cannot drift apart.
    expect(normalized).not.toContain('class="progress w-56 progress-success"')
  })

  it("routes every waiting screen's bar through the one readout component", () => {
    // Minting, grounding on each arm, both drive arms, both claims gates,
    // and the re-check.
    expect(normalized.split("<ProgressCount").length - 1).toBe(8)
  })

  it("counts the cases dropped from the review on both claims gates", () => {
    // A case the builder wrote without a verdict claim is excluded from the
    // review; a prompt that starts dropping verdicts has to be visible.
    expect(normalized.split("num_no_verdict:").length - 1).toBe(2)
  })
})

// ── The eval description, opened from the page header ──────────────────────
//
// The review step has no control of its own for the eval's text: the header's
// sub-line is the way in, so the reviewer looks up rather than into the work.
// The line and the action it fires are two props that must agree, and the
// dialog they open lives in the review component.
describe("the eval description opens from the page header", () => {
  it("shows the line only on review, and only with text to show", () => {
    expect(
      contains(
        'review_can_show_spec = current_step === "review" && current_spec_text.trim().length > 0',
      ),
    ).toBe(true)
    expect(contains('review_can_show_spec ? "Eval Description" : ""')).toBe(
      true,
    )
  })

  it("fires the review's own dialog, under the same condition as the line", () => {
    // Same flag on both, so the header can never render a line that opens
    // nothing — nor an action with no line to fire it.
    expect(
      contains(
        "sub_subtitle_action={review_can_show_spec ? () => review_component?.show_spec_dialog() : undefined}",
      ),
    ).toBe(true)
    expect(contains("bind:this={review_component}")).toBe(true)
  })
})

// ── The empty review subset ────────────────────────────────────────────────
describe("a review with nothing to grade is not a dead end", () => {
  it("names both causes and offers the save on a calibration round", () => {
    expect(normalized).toContain(
      "None of these ${judged_noun}s could be reviewed. Analyzing them either failed or produced no verdict to check.",
    )
    // First round: create the data again. Later rounds: that would throw away
    // grades the reviewer already gave, so the opt-out is offered instead.
    expect(normalized).toContain(
      'calibration_rounds_completed > 0 ? "" : " Create your eval data again."',
    )
    const branch = region(
      "{:else if reviewable_trace_indices.length === 0}",
      "{:else}",
    )
    expect(normalize(branch)).toContain("Save Without Improving")
    expect(normalize(branch)).toContain("on:click={save_without_refining}")
  })
})

// ── The forward action on the last case ───────────────────────────────────
//
// The reviewer's feedback can either improve the judge or be kept as-is. The
// wizard asks rather than deciding, and the dialog's secondary is the only way
// out of the refine loop, so these strings and both wirings are contractual.
describe("the improve-judge dialog", () => {
  // One action button's own object literal, from its label to the brace that
  // closes it. Asserting over the whole dialog cannot tell the two buttons
  // apart: swap their bodies and every string is still somewhere in the
  // region. This is what makes a swap fail.
  function action_button(label: string): string {
    const dialog = region('title="Improve Judge with Feedback?"', "</Dialog>")
    const at = dialog.indexOf(`label: "${label}"`)
    if (at < 0) throw new Error(`no action button labelled ${label}`)
    const end = dialog.indexOf("\n    },", at)
    if (end < 0) throw new Error(`unterminated action button ${label}`)
    return normalize(dialog.slice(at, end))
  }

  it("asks before refining, in the words the reviewer was promised", () => {
    const d = normalize(
      region('title="Improve Judge with Feedback?"', "</Dialog>"),
    )
    expect(d).toContain(
      "You disagreed with the judge and gave feedback, which we can use to improve your Judge.",
    )
    expect(d).toContain('label: "Improve Judge"')
    expect(d).toContain('label: "Save Without Improving"')
  })

  it("wires each button to the path it names, and only that path", () => {
    const improve = action_button("Improve Judge")
    expect(improve).toContain("isPrimary: true")
    expect(improve).toContain("run_calibration_round()")
    expect(improve).not.toContain("save_without_refining()")

    const save = action_button("Save Without Improving")
    expect(save).toContain("save_without_refining()")
    expect(save).not.toContain("run_calibration_round()")
    expect(save).not.toContain("isPrimary")
  })

  it("is what the keyboard shortcut reaches too", () => {
    // The shortcut fires the review's forward action rather than the save, so
    // a round with feedback is asked about however the reviewer triggers it.
    const keys = normalize(
      region("function handle_global_keydown(", "function step_name_for("),
    )
    expect(keys).toContain("save_gate_met && review_on_last_trace")
    expect(keys).toContain("on_advance_to_save()")
    expect(keys).not.toContain("on_save()")
  })

  it("opens only where the review asks to go forward with feedback", () => {
    // The dialog replaces the automatic refine: the decision point is the
    // same one, so it is opened from the same branch that used to calibrate.
    const advance = normalize(
      region("function on_advance_to_save()", 'goto_step("save")'),
    )
    expect(advance).toContain('decision.action === "calibrate"')
    expect(advance).toContain("improve_judge_dialog?.show()")
  })

  it("keeps no second exit beside the review's own action", () => {
    // The dialog's secondary is the only way past a review that has feedback;
    // the quiet link that used to sit under the review is gone. The empty-
    // subset screen keeps its own exit, because there is no review to go
    // forward from there at all.
    const review = normalize(
      region("<ClaimEvidenceReview", '{:else if current_step === "save"}'),
    )
    expect(review).not.toContain("Save Without Improving")
    expect(normalized).not.toContain("Save Without Refining Further")
  })
})

// ── The save's success screen ─────────────────────────────────────────────
describe("the eval-created screen", () => {
  it("finishes on the house success control rather than a redirect", () => {
    const done = normalize(region('title="Eval Created"', "/>"))
    expect(done).toContain(
      'subtitle="You\'ve created a new eval, including an eval dataset and aligned judge!"',
    )
    expect(done).toContain('button_text={created_eval_href ? "View Eval"')
    // A save with no id has no eval page to offer, so it points at the list.
    expect(done).toContain(
      "link={created_eval_href ?? `/specs/${project_id}/${task_id}`}",
    )
  })

  it("suppresses the leave guards by state, not by a latch", () => {
    // A latch that is only ever set stays set: a wizard that somehow returned
    // to a live step would be unguarded. The guard reads where the wizard is,
    // so it comes back on by itself.
    expect(normalized).toContain(
      '$: leave_guard_suppressed = resetting || current_step === "done"',
    )
    expect(normalized).not.toContain("leave_guard_suppressed = true")
  })

  it("makes the finished state terminal", () => {
    // The wizard stays mounted behind the success screen, so Back would
    // otherwise land on the graded review with its save gate met — one click
    // from a second Spec with the same batch tag, or a paid round on an eval
    // that already shipped.
    const sync = normalize(
      region("function sync_step_from_history(", "abort_copilot_request()"),
    )
    expect(sync).toContain("if (saved_eval_created) {")
    expect(sync).toContain("goto(finished_destination)")

    // And the state those two actions would need is dropped on the way in, so
    // a bug that got past the guard still has nothing to act on.
    const finish = normalize(
      region("function finish_on_done_screen(", 'replace_step("done")'),
    )
    expect(finish).toContain("saved_eval_created = true")
    expect(finish).toContain("trace_claims = []")
    expect(finish).toContain("trace_reviews = []")
  })

  it("finishes both save branches the same way, after the draft is cleared", () => {
    // Multi-turn and single-turn each end in their own save; both must land
    // on the same screen, and neither may do it while a draft still points at
    // the work that just shipped.
    expect(normalized.split("finish_on_done_screen(saved.id)").length - 1).toBe(
      2,
    )
    const save_body = normalize(
      region("async function on_save() {", "function create_manually()"),
    )
    // The clear is awaited before the flip, on both paths.
    expect(
      save_body.split("await clear_builder_draft(").length - 1,
    ).toBeGreaterThanOrEqual(2)
    const [first, second] = save_body.split("finish_on_done_screen(saved.id)")
    expect(first).toContain("await clear_builder_draft(")
    expect(second).toContain("await clear_builder_draft(")
  })
})

// The wizard's own copy: what each step is called, and what the screens the
// steps open on say while they work.
describe("wizard step copy", () => {
  const step_names = function_body(
    'function step_name_for(step: Exclude<BuilderStep, "save" | "done">): string {',
  )

  it("names each step after what the user does on it", () => {
    const named = normalize(step_names)
    expect(named).toContain('case "clarify": return "Clarify Eval"')
    expect(named).toContain('case "refine": return "Review Updated Eval"')
    expect(named).toContain('case "generate": return "Create Eval Dataset"')
  })

  it("asks the refine step's question in the header's second line", () => {
    // The step shows the eval rewritten from the user's answers, so the
    // header asks what the step exists to answer — and only there. The review
    // step's own second line is pinned separately, below.
    expect(
      contains(
        '$: page_sub_subtitle = current_step === "refine" ' +
          '? "We\'ve integrated your feedback, does it look right?" ' +
          ': review_can_show_spec ? "Eval Description" : ""',
      ),
    ).toBe(true)
    expect(contains("sub_subtitle={page_sub_subtitle}")).toBe(true)
  })

  it("says what the minting screen is making, and leaves the count to the bar", () => {
    // The progress bar under the line already carries how far along the run
    // is, so the sentence says what is being made and stops there.
    expect(contains('? "Creating Eval Dataset"')).toBe(true)
    expect(contains("? `Creating ${planned_total} dataset items.`")).toBe(true)
  })

  it("carries that name into the drive screen that follows, on both arms", () => {
    // Minting and driving are one stretch of work to someone watching it, so
    // the screen that follows the minting screen says the same thing it did.
    expect(page_source.match(/title="Creating Eval Dataset"/g)).toHaveLength(2)
    expect(page_source).not.toContain('title="Creating Eval Data"')
  })
})

// A drive that stopped with usable work left behind takes over the step: how
// much failed and the two ways out are the whole decision there. Every other
// stop kind keeps the banner over the plan, because its text is raw provider
// output and its way out runs through the plan.
describe("the stopped-drive screen", () => {
  const stop_step = region(
    "{#if drive_stop && is_partial_stop(drive_stop)}",
    "{:else if !generation_loading",
  )
  const partial_branch = stop_step.slice(0, stop_step.indexOf("{:else}"))
  const plan_branch = stop_step.slice(stop_step.indexOf("{:else}"))
  const stop_actions = region(
    "$: stop_lead = drive_stop",
    "[stop_rerun_action, stop_continue_action]",
  )

  it("takes over the step only for a stop that left usable work behind", () => {
    expect(normalize(partial_branch)).toContain(
      "{#if drive_stop && is_partial_stop(drive_stop)}",
    )
    expect(partial_branch).toContain("<Intro")
    expect(partial_branch).not.toContain("<Warning")
  })

  it("keeps the banner above the plan for every other stop kind", () => {
    // Preflight, abort and all-failed carry long raw provider text and a
    // recovery that runs through the plan, so the plan has to stay on screen.
    expect(plan_branch).toContain("<Warning")
    expect(plan_branch).toContain("<KilnProBatchPlan")
    // Always the error color here: what is left once the partial stop has
    // taken its own screen is a failed config or a failed batch.
    expect(normalize(plan_branch)).toContain('warning_color="error"')
    expect(plan_branch).not.toContain("is_partial_stop")
    expect(normalize(plan_branch)).toContain("markdown trusted")
  })

  it("demotes the plan's own primary while the Continue row is beside it", () => {
    // Two solid primaries on one screen is two leads. The plan's generate
    // button steps back to an outline whenever the survivors row co-renders.
    expect(normalize(plan_branch)).toContain(
      "generate_button_outline={has_driven_results && drive_stop !== null}",
    )
  })

  it("names the screen and hands it the two ways forward", () => {
    const screen = normalize(partial_branch)
    expect(screen).toContain('<Intro title="Errors During Dataset Creation"')
    expect(screen).toContain("action_buttons={stop_screen_actions}")
  })

  it("says what happened from the same source the banner uses", () => {
    // One function writes the sentence, so the screen and the banner can
    // never end up telling the same stop two different ways.
    expect(normalize(partial_branch)).toContain(
      "description_markdown={drive_stop_banner( drive_stop, " +
        "drive_run_config_name, drive_run_config_model, )}",
    )
    expect(partial_branch).not.toContain("description_paragraphs")
  })

  it("renders the leading action first and makes it the solid one", () => {
    // The house offer screen stacks its primary above the alternative, so the
    // order and the emphasis both come from the same decision.
    const actions = normalize(stop_actions)
    expect(actions).toContain(
      "label: `Continue With ${drive_stop?.survivors ?? 0}`, " +
        'onClick: on_continue_with_survivors, is_primary: stop_lead === "continue",',
    )
    expect(actions).toContain(
      'label: "Re-run Batch", onClick: open_drive_settings, ' +
        'is_primary: stop_lead === "rerun",',
    )
    expect(actions).toContain(
      '$: stop_screen_actions = stop_lead === "continue" ' +
        "? [stop_continue_action, stop_rerun_action] " +
        ": [stop_rerun_action, stop_continue_action]",
    )
  })

  it("swallows the keyboard shortcut instead of acting on it", () => {
    // The screen's buttons carry no shortcut hint, and which of them leads
    // changes with the batch, so the shortcut would fire an action the user
    // was never offered — on most of those batches a paid re-run. The
    // keystroke is consumed all the same, or a focused button takes the Enter.
    const shortcut = normalize(
      region(
        "if (drive_stop && is_partial_stop(drive_stop)) {",
        "if (has_driven_results) {",
      ),
    )
    expect(shortcut).toContain("event.preventDefault() return }")
    expect(shortcut).not.toContain("on_continue_with_survivors()")
    expect(shortcut).not.toContain("open_drive_settings()")
  })
})

// ── Builds whose run config reaches an OpenEnv server ─────────────────────
//
// Every case is checked against the server before it is driven. The flow's
// logic lives in grounding_flow.ts and its tests; these pin the page wiring.
describe("grounding a build's cases in its OpenEnv server", () => {
  const drive = function_body("async function on_drive_multi_turn() {")
  // cases_for_plan and its grounding half, in page order.
  const resolve_cases =
    function_body("async function cases_for_plan(") +
    function_body("async function ground_plan_cases(")

  it("asks for a tool-calling Environment Setup Model on an OpenEnv build, apart from the judge", () => {
    const d = normalize(drive_settings_dialog)
    expect(d).toContain(
      '{#if build_openenv_server_id !== null} <AvailableModelsDropdown label="Environment Setup Model"',
    )
    expect(d).toContain("requires_tool_support: true,")
    expect(d).not.toContain(
      "requires_tool_support: build_openenv_server_id !== null,",
    )
  })

  it("grounds freshly generated cases after generating them, before driving", () => {
    const generating = resolve_cases.indexOf(
      "generated_cases_for_plan(approved_prompts)",
    )
    const grounding = resolve_cases.indexOf(
      'generation_phase = "grounding_cases"',
    )
    expect(generating).toBeGreaterThan(0)
    expect(grounding).toBeGreaterThan(generating)
    expect(
      drive.indexOf('generation_phase = "running_pipeline"'),
    ).toBeGreaterThan(drive.indexOf("await cases_for_plan("))
  })

  it("reuses the grounded set only for the same server, model, thinking level and guide", () => {
    expect(normalize(resolve_cases)).toContain(
      "reusable_grounded_cases( cached_grounded_cases, approved_prompts, spec_text(), grounding_key, )",
    )
    expect(normalize(drive)).toContain(
      "const grounding_model: GroundingModel = { ...(grounding_lane_model ?? chosen_judge_model), thinking_level: grounding_lane_model ? grounding_thinking_level : null, }",
    )
    expect(normalize(drive)).toContain(
      "grounding_model: model_choice_key(grounding_model), data_guide: data_guide_in_use(), max_turns: grounding_turn_limit(chosen_turns),",
    )
  })

  it("shows a reused set's rehearsal verdicts only under the judge that gave them", () => {
    expect(normalize(resolve_cases)).toContain(
      "cases: cases_with_current_verdicts(grounded_cache, judge_key),",
    )
    expect(normalize(resolve_cases)).toContain(
      "...grounding_key, rehearsal_judge_key: judge_key,",
    )
  })

  it("grounds the cached generated cases rather than generating again", () => {
    // A grounding failure or a judge change misses the grounded set only:
    // the generated cases are cached on plan and spec alone.
    const generated = normalize(
      function_body("async function generated_cases_for_plan("),
    )
    expect(generated).toContain(
      "reusable_cached_cases( cached_su_cases, approved_prompts, spec_text(), data_guide_in_use(), )",
    )
    expect(normalize(resolve_cases)).toContain(
      "write: async () => grounding_key && !is_multi_turn ? plan_row_cases(approved_prompts) : await generated_cases_for_plan(approved_prompts),",
    )
  })

  it("reads the Data Guide again before every plan and drive uses it", () => {
    // An edit on the Data Guide page made after Step 4 opened must reach the
    // plan, the case writer and grounding, not the text read on entry.
    const plan = normalize(function_body("async function on_plan_batch("))
    expect(plan).toContain(
      "await refresh_data_guide(signal) const guidance = await plan_guidance(signal)",
    )
    for (const drive of [
      "async function on_drive_multi_turn(",
      "async function on_drive_single_turn(",
    ]) {
      const body = normalize(function_body(drive))
      const refresh = body.indexOf(
        "await refresh_data_guide(new_copilot_abort_signal())",
      )
      expect(refresh).toBeGreaterThan(-1)
      expect(refresh).toBeLessThan(
        body.indexOf("data_guide: data_guide_in_use()"),
      )
      expect(refresh).toBeLessThan(
        body.indexOf("author_judge_prompt_for_spec("),
      )
    }
    // Read where it is used, never from a reactive copy that a drive would
    // see a tick late.
    expect(contains("$: grounding_guide_text")).toBe(false)
  })

  it("starts the judge on its raised default, and grounding never copies it", () => {
    // The judge defaults to high thinking so it writes reasoning the review
    // can read; grounding runs once per case, so it keeps its model's own
    // default rather than paying for the judge's level.
    expect(
      contains("$: judge_model_details = with_judge_default_thinking_level("),
    ).toBe(true)
    expect(
      contains(
        "$: staged_judge_thinking_level = prefilled_judge_thinking_level( staged_judge_thinking_level, judge_model_details, false, )",
      ),
    ).toBe(true)
    for (const drive of [
      "async function on_drive_multi_turn(",
      "async function on_drive_single_turn(",
    ]) {
      expect(normalize(function_body(drive))).toContain(
        "thinking_level: grounding_lane_model ? grounding_thinking_level : null,",
      )
    }
    expect(
      normalize(function_body("async function open_drive_settings(")),
    ).toContain(
      "staged_grounding_thinking_level = grounding_lane_model ? grounding_thinking_level : null",
    )
    const fill = normalize(function_body("async function fill_null_lanes("))
    expect(fill).toContain(
      "grounding_lane_model = judge_model grounding_thinking_level = null",
    )
    expect(fill).not.toContain(
      "grounding_thinking_level = judge_thinking_level",
    )
  })

  it("checks the OpenEnv server answers before a drive spends anything", () => {
    for (const drive of [
      "async function on_drive_multi_turn(",
      "async function on_drive_single_turn(",
    ]) {
      const body = normalize(function_body(drive))
      const check = body.indexOf(
        "openenv_server_id !== null && !(await openenv_server_answers(openenv_server_id))",
      )
      expect(check).toBeGreaterThan(-1)
      expect(check).toBeLessThan(body.indexOf("author_judge_prompt_for_spec("))
    }
  })

  it("warns in Generation Settings when the server offers no reset arguments", () => {
    const dialog = region(
      '<Dialog bind:this={drive_settings_dialog} title="Generation Settings">',
      "</Dialog>",
    )
    expect(normalize(dialog)).toContain(
      '{#if reset_arguments_warning} <Warning warning_color="warning" warning_message={reset_arguments_warning} /> {/if}',
    )
    // The reset schema, not the brief: a seed-only schema has an empty brief
    // and must get no note.
    const open = normalize(function_body("async function open_drive_settings("))
    expect(open).toContain(
      "await load_openenv_server_reset_schema( project_id, openenv_server_id, )",
    )
    expect(open).toContain(
      "reset_schema_read = { openenv_server_id, published: schema !== null }",
    )
    expect(open).toContain(
      "reset_schema_read = { openenv_server_id, published: null }",
    )
  })

  it("gives the case writer the Data Guide the drive uses", () => {
    // The writer of each simulated user's first message and persona reads the
    // guide only through generate_cases, so a first-message rule in it (a
    // ticket id, say) would otherwise never reach the cases.
    expect(
      normalize(function_body("async function request_generated_cases(")),
    ).toContain(
      "target_specification: spec_text(), case_prompts, data_guide: data_guide_in_use() || null,",
    )
    // The guide goes as its own field and the spec stays plain, so the judge
    // author, which reads the spec, never gets the guide.
    const judge_author = function_body(
      "async function author_judge_prompt_for_spec(",
    )
    expect(judge_author).toContain("const spec = spec_text()")
    expect(judge_author).not.toContain("data_guide")
  })

  it("never looks a build up without an OpenEnv tool", () => {
    expect(function_body("async function ensure_openenv_server(")).toContain(
      "if (!tool_ids.some(is_openenv_tool_id)) return null",
    )
  })

  it("drives the cases that fit, keeping the drops with the grounded set", () => {
    const r = normalize(resolve_cases)
    expect(r).toContain(
      "if (outcome.grounded.length === 0) { grounding_all_dropped = outcome.drops return null }",
    )
    expect(r).toContain(
      "return { cases: outcome.grounded, grounding_drops: outcome.drops.length }",
    )
    expect(r).toContain(
      "grounding_dropped: outcome.drops.length, drops: outcome.drops, drops_notice_seen: false,",
    )
    // Only the all-dropped case stops, and it stops before anything is
    // committed, so the previous drive's results stay as they were.
    const d = normalize(drive)
    expect(d).toContain("if (resolved === null) return")
    expect(d.indexOf("await cases_for_plan(")).toBeLessThan(
      d.indexOf("drive_committed = true"),
    )
    // The drops count as planned-for, not failed, so no stop screen follows.
    expect(d).toContain(": approved_prompts.length - drive_grounding_drops")
  })

  it("shows the checking progress with the dropped count", () => {
    expect(contains('noun="cases ready"')).toBe(true)
    expect(contains('failed_label="dropped"')).toBe(true)
    expect(contains("Preparing Your Test Cases")).toBe(true)
  })

  it("sends Step 4 back to planning when every case dropped", () => {
    expect(
      contains(
        "<DropsRefineScreen dropped={batch_plan.prompts.length} planned={batch_plan.prompts.length} noun={planned_noun}",
      ),
    ).toBe(true)
    expect(
      contains("open_refine_plan_after_drops(grounding_all_dropped)}"),
    ).toBe(true)
    // The plan, its Continue and the keyboard's forward action all stand
    // down while it shows.
    expect(
      normalize(
        region("$: show_plan_approval =", "claims_gate_error === null"),
      ),
    ).toContain("grounding_all_dropped === null")
    expect(
      contains(
        "{:else if !generation_loading && !generation_error && !grounding_all_dropped &&",
      ),
    ).toBe(true)
    expect(
      contains(
        "} else if ( !generation_error && !claims_gate_error && !grounding_all_dropped ) {",
      ),
    ).toBe(true)
  })

  it("opens Refine Plan with the drops and the same steer", () => {
    const refine = normalize(
      function_body("function open_refine_plan_after_drops("),
    )
    expect(refine).toContain("refine_from_drops = drops")
    expect(refine).toContain("plan_steer = landed_plan_steer")
    expect(refine).toContain("open_new_plan_dialog()")
    expect(
      contains(
        "$: new_plan_warning = refine_from_drops ? refine_after_drops_confirm({",
      ),
    ).toBe(true)
  })

  describe("the review's dropped-conversations warning", () => {
    it("shows on the review start screen for the set the batch was driven from", () => {
      const due = normalize(region("$: notice_drops =", "    : null"))
      expect(due).toContain('current_step === "review"')
      expect(due).toContain(
        "dropped_notice_drops(cached_grounded_cases, driven_prompts_json)",
      )
      expect(
        contains(
          "dropped_notice(notice_drops.length, driven_plan_size, planned_noun)",
        ),
      ).toBe(true)
      expect(
        contains(
          "{:else if !review_intro_dismissed || drops_warning} <ReviewIntro",
        ),
      ).toBe(true)
      expect(
        contains(
          "{drops_warning} drops_action={review_drops_action} kept_count={trace_claims.length} on_start={start_review}",
        ),
      ).toBe(true)
    })

    it("is marked seen on Continue and on Refine Plan, on the drafted grounded set", () => {
      expect(
        normalize(function_body("function mark_dropped_notice_seen() {")),
      ).toContain(
        "cached_grounded_cases = { ...cached_grounded_cases, drops_notice_seen: true, }",
      )
      expect(normalize(function_body("function start_review() {"))).toContain(
        "mark_dropped_notice_seen()",
      )
      const refine = normalize(
        function_body("function refine_plan_from_notice() {"),
      )
      expect(refine).toContain("mark_dropped_notice_seen()")
      expect(refine.indexOf("history.back()")).toBeLessThan(
        refine.indexOf("open_refine_plan_after_drops(drops)"),
      )
      expect(contains("on_refine_plan={refine_plan_from_notice}")).toBe(true)
    })
  })

  // The dropped cases guide only the plan their Refine Plan starts. A failed
  // plan leaves them in place for the error screen's Retry, which re-tries
  // that plan; any other new plan must not inherit them.
  describe("the dropped cases a Refine Plan adds to the plan", () => {
    const clear = "pending_retry_drops = []"

    it("are cleared once a plan lands, not when one starts", () => {
      const plan = function_body("async function on_plan_batch() {")
      expect(plan.indexOf(clear)).toBeGreaterThan(
        plan.indexOf("batch_plan = planned"),
      )
    })

    it("are cleared when the user leaves the step", () => {
      expect(function_body("function sync_step_from_history(")).toContain(clear)
    })

    it("are cleared by Refine Plan unless it opened because of drops", () => {
      expect(function_body("function submit_new_plan() {")).toContain(
        "pending_retry_drops = refine_from_drops ?? []",
      )
    })

    it("survive the error screen's Retry of a failed plan", () => {
      expect(
        function_body("function on_continue_from_generate_step() {"),
      ).not.toContain("pending_retry_drops")
    })
  })

  it("adds the reset arguments and dropped cases sections to the plan", () => {
    const guidance = normalize(function_body("async function plan_guidance("))
    expect(guidance).toContain("reset_arguments_section(")
    expect(guidance).toContain("dropped_cases_section(pending_retry_drops)")
    const guide = guidance.indexOf(
      "data_guide_section(use_data_guide ? data_guide_text : null)",
    )
    expect(guide).toBeGreaterThan(guidance.indexOf("reset_arguments_section("))
    expect(guide).toBeLessThan(guidance.indexOf("dropped_cases_section("))
    expect(guidance).toContain("const openenv = openenv_server_id !== null")
    expect(guidance).toContain(
      "multiturn_plan_guidance(spec_text(), { openenv }) : single_turn_plan_guidance(spec_text(), { openenv }),",
    )
    expect(guidance).toContain("pending_plan_steer,")
  })

  describe("on a single-turn build", () => {
    const single_drive = function_body(
      "async function on_drive_single_turn() {",
    )

    it("runs grounded cases as its inputs instead of minting them", () => {
      const d = normalize(single_drive)
      expect(d).toContain(
        "const openenv_server_id = await ensure_openenv_server( drive_config.tool_ids, )",
      )
      expect(d).toContain(
        "items = single_turn_items_from_cases(resolved.cases) planned_inputs -= resolved.grounding_drops",
      )
      expect(d.indexOf("await cases_for_plan(")).toBeLessThan(
        d.indexOf("drive_committed = true"),
      )
      expect(d).toContain("...single_turn_pipeline_inputs(drive_plan.items),")
    })

    it("asks for no input generation model when it grounds its inputs", () => {
      expect(
        contains("{:else if !grounds_single_turn} <RunConfigComponent"),
      ).toBe(true)
      expect(
        contains(
          "$: grounds_single_turn = !is_multi_turn && build_openenv_server_id !== null",
        ),
      ).toBe(true)
    })

    it("saves each input's episode and guidance with the server", () => {
      expect(
        contains("openenv_server_id: grounded_server_id(trace_claims),"),
      ).toBe(true)
      expect(contains("openenv_reset: tc.openenv_reset ?? null,")).toBe(true)
    })

    it("shows the checking progress in inputs", () => {
      expect(contains('noun="inputs ready"')).toBe(true)
    })
  })

  it("passes each case's guidance to the claims build and the re-judge", () => {
    expect(contains("judge_guidance: tc.judge_guidance ?? null,")).toBe(true)
    expect(
      contains("judge_guidance: rejudge_guidance(entries.map((e) => e.i)),"),
    ).toBe(true)
  })

  it("saves the server the cases were grounded in", () => {
    expect(
      contains("openenv_server_id: grounded_server_id(driven_cases),"),
    ).toBe(true)
  })

  it("keeps the server lookup across a reload, but reads the brief afresh", () => {
    const mirror = normalize(
      region("$: current_draft = draft_ready", "    : null"),
    )
    expect(mirror).toContain("openenv_server_lookup,")
    expect(mirror).not.toContain("reset_arguments_brief")
    expect(mirror).toContain("landed_plan_steer,")
    expect(mirror).toContain("cached_grounded_cases,")
  })
})

describe("the task's Data Guide on a multi-turn build", () => {
  it("offers the guide on multi-turn too, and writes it in a dialog", () => {
    expect(
      normalize(function_body("async function plan_or_offer_data_guide(")),
    ).not.toContain("if (is_multi_turn)")
    expect(normalize(function_body("function set_up_data_guide("))).toContain(
      "if (is_multi_turn) { data_guide_text_dialog?.show(legacy_guide_prefill) return }",
    )
    expect(contains("on_saved={on_multi_turn_guide_saved}")).toBe(true)
  })

  it("plans under the guide once it is saved", () => {
    const saved = normalize(
      function_body("function on_multi_turn_guide_saved("),
    )
    expect(saved).toContain("use_data_guide = data_guide_text !== null")
    expect(saved).toContain("if (data_guide_text !== null) on_plan_batch()")
  })

  it("offers the guide's own words on multi-turn", () => {
    expect(
      contains(
        "{...is_multi_turn ? { description_paragraphs: MULTI_TURN_GUIDE_OFFER } : {}}",
      ),
    ).toBe(true)
  })

  it("no longer asks who uses the agent in Generation Settings", () => {
    expect(contains('label="Who uses this agent"')).toBe(false)
  })

  it("links the task's guide from the page header when there is one", () => {
    expect(
      contains(
        '...(data_guide_text !== null ? [ { label: "Data Guide", href: with_data_guide_caller( `/generate/${project_id}/${task_id}/data_guide`, "builder", ), }, ] : []),',
      ),
    ).toBe(true)
  })
})

describe("a task with a JSON input schema on an OpenEnv build", () => {
  it("grounds it like any single-turn task: the grounding agent writes JSON inputs", () => {
    expect(
      normalize(function_body("async function on_drive_single_turn() {")),
    ).not.toContain("task?.input_json_schema")
  })
})

describe("Generation Settings: the rehearsal check", () => {
  const dialog = () =>
    region(
      '<Dialog bind:this={drive_settings_dialog} title="Generation Settings">',
      "</Dialog>",
    )

  it("offers the box only on an OpenEnv build, bound to the staged copy", () => {
    expect(normalize(dialog())).toContain(
      normalize(`{#if build_openenv_server_id !== null}
      <FormElement
        id="check_rehearsals"
        label="Check Rehearsals"
        inputType="checkbox"
        bind:value={staged_check_rehearsals}`),
    )
  })

  it("starts off, also on an older draft, is reseeded on open and committed on submit", () => {
    expect(contains("let check_rehearsals = false")).toBe(true)
    expect(contains("check_rehearsals = saved.check_rehearsals ?? false")).toBe(
      true,
    )
    expect(function_body("async function open_drive_settings(")).toContain(
      "staged_check_rehearsals = check_rehearsals",
    )
    expect(function_body("async function submit_drive_settings() {")).toContain(
      "check_rehearsals = staged_check_rehearsals",
    )
  })

  it("quotes the extra judge calls in the cost warning while the box is on", () => {
    expect(
      contains(`checks_rehearsals:
      build_openenv_server_id !== null && staged_check_rehearsals,`),
    ).toBe(true)
  })

  it("sends the build's judge to grounding only while the box is on", () => {
    expect(mentions("check_rehearsals ? judge : null")).toBe(2)
  })
})

describe("Generation Settings: Pilot First", () => {
  const dialog = () =>
    region(
      '<Dialog bind:this={drive_settings_dialog} title="Generation Settings">',
      "</Dialog>",
    )

  it("offers the box on a multi-turn build only, bound to the staged copy", () => {
    expect(normalize(dialog())).toContain(
      normalize(`{#if is_multi_turn}
      <FormElement
        id="pilot_first"
        label="Pilot First"
        inputType="checkbox"
        bind:value={staged_pilot_first}`),
    )
  })

  it("starts off, also on an older draft, is reseeded on open and committed on submit", () => {
    expect(contains("let pilot_first = false")).toBe(true)
    expect(contains("pilot_first = saved.pilot_first ?? false")).toBe(true)
    expect(function_body("async function open_drive_settings(")).toContain(
      "staged_pilot_first = pilot_first",
    )
    expect(function_body("async function submit_drive_settings() {")).toContain(
      "pilot_first = staged_pilot_first",
    )
  })

  it("asks the owner only through write_review_ground, and only with the box on", () => {
    const resolve = normalize(function_body("async function cases_for_plan("))
    expect(resolve).toContain(
      "return write_review_ground<SyntheticUserCaseWire, PlanCases>({ pilot_first: pilot_first && is_multi_turn,",
    )
    expect(resolve).toContain("review: review_first_messages,")
    // Defined once and handed over once, imported once and called once: no
    // other path stops a build.
    expect(mentions("review_first_messages")).toBe(2)
    expect(mentions("write_review_ground")).toBe(2)
  })

  it("shows the first messages inside the generate progress screen, not as a new step", () => {
    expect(
      contains(
        '{#if generation_loading && generation_phase === "reviewing_first_messages" && first_messages_cases} <!--',
      ),
    ).toBe(true)
    expect(
      contains(
        'on_continue={() => first_messages_gate.choose("continue")} on_refine={() => first_messages_gate.choose("refine")}',
      ),
    ).toBe(true)
    // The wizard's steps are unchanged.
    expect(contains('current_step === "reviewing_first_messages"')).toBe(false)
  })

  it("waits on the page's abort signal, so Back cancels the wait", () => {
    expect(
      normalize(function_body("async function review_first_messages(")),
    ).toContain("await first_messages_gate.wait(new_copilot_abort_signal())")
  })
})

describe("Pilot First: the pilot of 12", () => {
  const resolve = () =>
    normalize(function_body("async function cases_for_plan("))
  const drive = () =>
    normalize(function_body("async function on_drive_multi_turn() {"))

  it("splits off a pilot only with the box on, on a multi-turn build", () => {
    expect(resolve()).toContain(
      "const split = pilot_first && is_multi_turn ? split_pilot(cases) : null",
    )
    expect(mentions("split_pilot(")).toBe(1)
  })

  it("decides rest or retry from the pilot state, before the grounded cache", () => {
    const body = resolve()
    expect(body).toContain(
      "const pilot_step = pilot_next_step({ pilot_state, key, batch_items: batch_cases, built_slots: built_by_case, })",
    )
    expect(body.indexOf("pilot_next_step(")).toBeLessThan(
      body.indexOf("if (grounded_cache) {"),
    )
    expect(contains("pilot_rest_requested")).toBe(false)
    // The panel's Continue opens the settings dialog like every other way
    // in, which stays the drive's only entrance; a second click does nothing.
    expect(
      normalize(function_body("function continue_after_pilot() {")),
    ).toContain(
      'if (current_step !== "review") return history.back() void open_drive_settings()',
    )
    expect(mentions("on_drive_multi_turn")).toBe(2)
  })

  it("clears the pilot only once a drive that is not the pilot commits", () => {
    const d = drive()
    expect(d).toContain("if (!resolved.pilot) pilot_state = null")
    expect(
      d.indexOf("if (!resolved.pilot) pilot_state = null"),
    ).toBeGreaterThan(d.indexOf("drive_committed = true"))
    expect(
      normalize(function_body("async function run_pilot_rest(")),
    ).not.toContain("pilot_state = null")
  })

  it("reuses a rest grounded before, so its grounding is not paid twice", () => {
    expect(
      normalize(function_body("async function run_pilot_rest(")),
    ).toContain(
      "if (grounded_cache) { return { cases: cases_with_current_verdicts(grounded_cache, judge_key), grounding_drops: grounded_cache.grounding_dropped, after_pilot: state.pilot_cases, }",
    )
  })

  it("blocks saving the pilot as the eval, and says why", () => {
    expect(
      contains(
        "$: save_gate_met = // Pilot First: a pilot is not the eval; its rest runs first. !pilot_batch_pending &&",
      ),
    ).toBe(true)
    expect(
      normalize(function_body("function on_advance_to_save() {")),
    ).toContain("if (pilot_batch_pending) return")
    expect(
      normalize(function_body("function save_without_refining() {")),
    ).toContain("if (pilot_batch_pending) return")
    expect(
      contains(
        "warning_message={pilot_save_blocked_text( pilot_state.rest.length, )}",
      ),
    ).toBe(true)
  })

  it("plans a pilot drive for its own cases and widens only for the rest", () => {
    expect(drive()).toContain(
      "planned_cases = resolved.pilot ? cases.length : approved_prompts.length - drive_grounding_drops",
    )
    expect(drive()).toContain(
      "batch_items: lanes_unchanged ? widened?.batch_items ?? batch_cases : null, built_slots: widened?.built_slots ?? built_by_case,",
    )
    expect(drive()).toContain("const widened = resolved.after_pilot ?")
  })

  it("never caches a pilot as the plan's grounded set", () => {
    const pilot = normalize(function_body("async function run_pilot("))
    expect(pilot).not.toContain("cached_grounded_cases =")
    expect(
      normalize(function_body("async function run_pilot_rest(")),
    ).toContain("cached_grounded_cases = {")
  })

  it("shows the pilot stop above the eval check panel on the review start screen", () => {
    expect(
      contains(`{#if pilot_batch_pending && pilot_state}
                  <div class="mb-6">
                    <PilotStop`),
    ).toBe(true)
    expect(page_source.indexOf("<PilotStop")).toBeLessThan(
      page_source.indexOf("<EvalCheckPanel"),
    )
  })
})
