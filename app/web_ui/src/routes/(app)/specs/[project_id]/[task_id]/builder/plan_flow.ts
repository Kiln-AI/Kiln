// Step 4 plan-flow state logic, extracted pure so the stop screen and the
// preparing-review gate are unit-testable: the stop banner's wording, the
// three-tier destructive-action confirms, and the gate's resolved counting.

import type { ClaimsBuildState } from "./claim_evidence"

// The unified stop outcome: a drive that ended short of the approved plan.
// survivors = judged conversations; failed = post-retry case failures plus
// upstream salvage drops.
export type DriveStop = {
  survivors: number
  failed: number
  dominant_error: string | null
  // Set when a config-scoped failure aborted the whole batch server-side
  // (the batch_aborted frame) — the banner then leads with the abort
  // diagnosis instead of per-case counts.
  aborted_error?: string | null
}

// Dominant per-case error: the most frequent case_failed message.
// Config-class failures repeat identically, so the mode IS the diagnosis;
// ties resolve to the first seen. Blank messages are ignored.
export function dominant_failure_message(messages: string[]): string | null {
  const counts = new Map<string, number>()
  for (const m of messages) {
    if (!m) continue
    counts.set(m, (counts.get(m) ?? 0) + 1)
  }
  let best: string | null = null
  let best_count = 0
  for (const [m, c] of counts) {
    if (c > best_count) {
      best = m
      best_count = c
    }
  }
  return best
}

// The stop banner's message. Rendered via Warning's markdown+trusted mode
// so the all-failed variant can carry the run-page deeplink in-message —
// markdown links open in a new tab by component design, so the wizard tab
// (and the plan behind it) survive the detour. The recovery sentence is
// its own PARAGRAPH (blank markdown line): raw error text can be long
// (full provider messages ride through unfiltered), and the action must
// never drown in the diagnosis.
export function drive_stop_banner(
  stop: DriveStop,
  run_config_name: string | null,
  run_config_model: string | null = null,
): string {
  const config_clause = run_config_name
    ? ` (run config: ${run_config_name})`
    : ""
  if (stop.aborted_error) {
    // A config-scoped failure aborted the batch mid-drive: the run config
    // (name + model) IS the diagnosis, and cases judged before the abort
    // remain valid survivors.
    const abort_config = run_config_name
      ? ` (run config: ${run_config_name}${
          run_config_model ? `, ${run_config_model}` : ""
        })`
      : ""
    const recovery =
      stop.survivors > 0
        ? `${stop.survivors} conversation${
            stop.survivors === 1 ? "" : "s"
          } completed before the abort — continue with those, or [test your run config](/run) and drive again.`
        : `You can [test your run config](/run), then drive again.`
    return `Drive aborted — ${stop.aborted_error}${abort_config}.\n\n${recovery}`
  }
  if (stop.survivors === 0) {
    // Every case failed identically — a capability boundary of the run
    // config, not bad luck. Point at the one place it can be verified.
    return `All conversations failed — ${
      stop.dominant_error ?? "no error details"
    }${config_clause}.\n\nYou can [test your run config](/run), then drive again.`
  }
  const total = stop.survivors + stop.failed
  const common_clause = stop.dominant_error
    ? ` (most common: ${stop.dominant_error})`
    : ""
  return `${stop.survivors} of ${total} conversations completed — ${stop.failed} failed after retries${common_clause}.\n\nContinue with the ${stop.survivors} that completed, or drive the batch again.`
}

// SDG's confirm formula for the destructive tier that carries real work.
// The review-progress clause applies only once the user accepted the
// results (was in review) — on the stop screen no review exists yet.
export function driven_data_confirm(
  action: string,
  survivors: number,
  include_review_progress: boolean,
): string {
  const progress_clause = include_review_progress
    ? " and your review progress"
    : ""
  return `You have ${survivors} driven conversation${
    survivors === 1 ? "" : "s"
  }${progress_clause}. ${action} will discard them. This cannot be undone.`
}

// New Batch Plan ALWAYS confirms — a plan alone costs minutes to make.
// Three-tier wording: what you lose scales the message — plan only /
// plan + row deletions / driven conversations. The first two tiers are
// SDG's exact formulas.
export function new_plan_confirm(state: {
  has_driven_results: boolean
  survivors: number
  include_review_progress: boolean
  plan_edited: boolean
}): string {
  if (state.has_driven_results) {
    return driven_data_confirm(
      "A new plan",
      state.survivors,
      state.include_review_progress,
    )
  }
  return state.plan_edited
    ? "Are you sure you want to discard the current batch plan, including the dataset items you removed? This cannot be undone."
    : "Are you sure you want to discard the current batch plan? This cannot be undone."
}

// ── The preparing-review gate ────────────────────────────────────────────

// A trace holds the gate only while its claims could still change: "built"
// and "error" are both RESOLVED (errored builds keep their in-review
// error+retry card and must not hold the door).
export function is_claims_resolved(state: ClaimsBuildState): boolean {
  return state === "built" || state === "error"
}

// How many of the selected traces are resolved — the gate advances (and
// the "Preparing review — N of M ready" count line fills) when this
// reaches selected_indices.length.
export function resolved_selected_count(
  traces: { claims_state: ClaimsBuildState }[],
  selected_indices: number[],
): number {
  return selected_indices.filter((i) => {
    const t = traces[i]
    return t !== undefined && is_claims_resolved(t.claims_state)
  }).length
}
