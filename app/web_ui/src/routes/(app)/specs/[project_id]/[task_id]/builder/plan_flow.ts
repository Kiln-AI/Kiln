// Step 4 plan-flow state logic, extracted pure so the stop screen and the
// preparing-review gate are unit-testable: the stop banner's wording, the
// three-tier destructive-action confirms, and the gate's resolved counting.

import type { ClaimsBuildState } from "./claim_evidence"

// The three model lanes a drive spends through, checked before anything
// runs. Lane order IS blame order: the target run config is the likeliest
// culprit and the one the user can fix in-app.
export type PreflightLane = "run config" | "synthetic-user driver" | "judge"

export type PreflightOutcome = {
  lane: PreflightLane
  ok: boolean
  // The failure diagnosis (the route's unwrapped root provider error).
  message?: string | null
  // The lane's model ("gpt_4o via openrouter") — kept for telemetry;
  // Kiln-chosen lanes don't render it.
  model?: string | null
  // The lane's provider display name ("OpenRouter") — the one specific,
  // factual thing the generic lanes DO render: which key the step needs.
  provider?: string | null
}

export type PreflightFailure = {
  lane: PreflightLane
  message: string
  model: string | null
  provider: string | null
}

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
  // Set when a lane failed its pre-drive check: NOTHING ran — no cases
  // generated, no spend. The banner leads with the lane's diagnosis.
  preflight?: PreflightFailure | null
}

// The one failure the banner reports, chosen in the given (blame) order —
// deterministic regardless of which lane's ping lost the race. All lanes
// are checked concurrently, so with several dead lanes the user fixes them
// front-to-back across re-drives.
export function first_preflight_failure(
  outcomes: PreflightOutcome[],
): PreflightFailure | null {
  const failed = outcomes.find((o) => !o.ok)
  if (!failed) return null
  return {
    lane: failed.lane,
    message: failed.message || "the model did not respond",
    model: failed.model ?? null,
    provider: failed.provider ?? null,
  }
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
  if (stop.preflight) {
    // A lane failed its pre-drive test call: nothing ran and nothing was
    // spent. All lanes show the raw error (the SDG precedent — generation
    // failures render getMessage() verbatim), with a parenthetical naming
    // what was tested: the run config (name + model) on the user's lane,
    // the model on the Kiln-chosen lanes. Recovery is the banner family's
    // deeplink formula; the Kiln-chosen lanes also state the one
    // requirement fact we know (which provider's key the step runs on).
    const f = stop.preflight
    if (f.lane === "run config") {
      const clause = run_config_name
        ? ` (run config: ${run_config_name}${
            run_config_model ? `, ${run_config_model}` : ""
          })`
        : ""
      return `Could not create your eval data. Your run config failed a test call: ${f.message}${clause}.\n\nYou can [test your run config](/run), then start again.`
    }
    const subject =
      f.lane === "synthetic-user driver"
        ? "The model that plays the user"
        : "The judge model"
    const model_clause = f.model ? ` (${f.model})` : ""
    const requirement = f.provider
      ? `Creating your eval data requires your ${f.provider} API key. `
      : ""
    return `Could not create your eval data. ${subject} failed a test call: ${f.message}${model_clause}.\n\n${requirement}You can [check your model providers](/settings/providers), then try again.`
  }
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
          } completed before the stop. Continue with those, or [test your run config](/run) and run the batch again.`
        : `You can [test your run config](/run), then run the batch again.`
    return `The run was stopped: ${stop.aborted_error}${abort_config}.\n\n${recovery}`
  }
  if (stop.survivors === 0) {
    // Every case failed identically — a capability boundary of the run
    // config, not bad luck. Point at the one place it can be verified.
    return `All conversations failed: ${
      stop.dominant_error ?? "no error details"
    }${config_clause}.\n\nYou can [test your run config](/run), then run the batch again.`
  }
  const total = stop.survivors + stop.failed
  const common_clause = stop.dominant_error
    ? ` (most common: ${stop.dominant_error})`
    : ""
  return `${stop.survivors} of ${total} conversations completed. ${stop.failed} failed after retries${common_clause}.\n\nContinue with the ${stop.survivors} that completed, or run the batch again.`
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
  return `You have ${survivors} completed eval input${
    survivors === 1 ? "" : "s"
  }${progress_clause}. ${action} will discard them. This cannot be undone.`
}

// New Scenarios ALWAYS confirms — a plan alone costs minutes to make.
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
      "New scenarios",
      state.survivors,
      state.include_review_progress,
    )
  }
  return state.plan_edited
    ? "Are you sure you want to discard the current scenarios, including the ones you removed? This cannot be undone."
    : "Are you sure you want to discard the current scenarios? This cannot be undone."
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
