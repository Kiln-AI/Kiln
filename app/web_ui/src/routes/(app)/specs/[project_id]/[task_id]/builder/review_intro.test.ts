// Source assertions for Step 5's entry screen. Same house precedent as
// generate_step_surface.test.ts: the builder page is too large to mount, and
// these are contractual — the reviewer supplied this copy word for word, and
// asked for the shared Intro control by name rather than a bespoke screen.
import { describe, expect, it } from "vitest"
import * as fs from "fs"
import * as path from "path"

const intro_source = fs.readFileSync(
  path.resolve(__dirname, "./review_intro.svelte"),
  "utf-8",
)
const page_source = fs.readFileSync(
  path.resolve(__dirname, "./+page.svelte"),
  "utf-8",
)

// Collapses whitespace so an assertion survives Prettier rewrapping a long
// attribute across lines.
function normalize(source: string): string {
  return source.replace(/\s+/g, " ")
}

describe("Step 5 entry screen", () => {
  it("is built on the shared Intro control, not a bespoke screen", () => {
    // Asked for by name. A hand-rolled version drifted on width, type scale,
    // icon treatment and button style, and read as foreign on sight.
    expect(intro_source).toContain('import Intro from "$lib/ui/intro.svelte"')
    expect(normalize(intro_source)).toContain("<Intro")
  })

  it("keeps the reviewer's copy word for word", () => {
    const normalized = normalize(intro_source)
    expect(normalized).toContain('title="Align the Judge"')
    expect(normalized).toContain(
      "Let's confirm your judge is aligned to your expectations.",
    )
    // The noun is the one substitution: he wrote "examples", which is wrong on
    // the multi-turn arm where every item is a whole conversation.
    expect(normalized).toContain(
      "We'll show a set of ${judged_noun}s, and you tell us if you agree with its judgement.",
    )
  })

  it("with drops, shows the warning, and drops_action picks the buttons", () => {
    const normalized = normalize(intro_source)
    expect(normalized).toContain(
      '<Warning warning_color="warning" warning_message={drops_warning} />',
    )
    expect(normalized).toContain(
      "action_buttons={buttons(drops_warning, drops_action, kept_count)}",
    )
    // Few drops: Continue leads.
    expect(normalized).toContain(
      '{ label: "Continue", onClick: on_start, is_primary: true }, { ...refine, is_primary: false },',
    )
    // Over 15%: Refine Plan leads, and Continue says how many it keeps.
    expect(normalized).toContain(
      "{ ...refine, is_primary: true }, { label: `Continue with ${kept}`, onClick: on_start, is_primary: false, },",
    )
    // Half or more never reaches this screen: the refine screen replaces it.
    expect(normalize(page_source)).toContain(
      '{#if drops_warning && review_drops_action === "refine_only"} <DropsRefineScreen',
    )
  })

  it("offers one primary action, labelled Start", () => {
    const normalized = normalize(intro_source)
    expect(normalized).toContain('label: "Start"')
    expect(normalized).toContain("is_primary: true")
  })

  it("fronts the review rather than replacing it", () => {
    // The intro is shown once per arrival and then hands over to the grading
    // surface. If this inverts, the reviewer never reaches the claims.
    const normalized = normalize(page_source)
    expect(normalized).toContain(
      "{:else if !review_intro_dismissed || drops_warning} <ReviewIntro",
    )
    expect(normalized).toContain("on_start={start_review}")
  })

  it("carries the eval check panel under it, which Start skips", () => {
    // The panel sits on this screen rather than in a step of its own, and
    // only while the entry screen shows: Start dismisses both together.
    const normalized = normalize(page_source)
    expect(normalized).toMatch(
      /on_refine_plan=\{refine_plan_from_notice\} \/> <div class="max-w-4xl mx-auto mt-12"> \{#if pilot_batch_pending && pilot_state\}[\s\S]*?\{\/if\} <EvalCheckPanel cases=\{trace_claims\}/,
    )
  })

  it("does not persist the dismissal", () => {
    // Per arrival, not per user: a reviewer who reloads has lost the context
    // along with the page, so the screen earns its place again.
    expect(intro_source).not.toContain("localStorage")
    expect(intro_source).not.toContain("sessionStorage")
  })
})
