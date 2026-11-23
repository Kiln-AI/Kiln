// Replace Dropped Cases on an OpenEnv build: new scenarios take the dropped
// rows' places in the plan, so the cases that fit keep their rows, and both
// case caches can be rebuilt for the merged plan from the kept cases plus the
// replacements alone.

import type { GroundingDrop } from "./batch_plan_guidance"
import type { SyntheticUserCaseWire } from "./builder_draft"
import { throw_if_aborted, unless_aborted } from "./plan_flow"

// A dropped plan row and the new scenario planned for it.
export type Replacement = { row: number; scenario: string }

// The drop reason for a replacement kiln_server's generate step skipped
// (its salvage drops a case it can't write rather than failing the batch).
export const SIMULATED_USER_MISSING_DETAIL =
  "Kiln couldn't write a simulated user for this scenario."

// The plan's scenarios that stay in the batch: every row that didn't drop.
export function kept_scenarios(
  prompts: string[],
  drops: GroundingDrop[],
): string[] {
  const dropped = new Set(drops.map((d) => d.scenario_index))
  return prompts.filter((_, row) => !dropped.has(row))
}

// Pairs the dropped rows, in plan order, with the planner's new scenarios
// and swaps each into its row. The planner can return fewer than asked for:
// a drop left without a scenario stays in the plan and stays dropped.
export function plan_replacements(
  prompts: string[],
  drops: GroundingDrop[],
  new_prompts: string[],
): {
  prompts: string[]
  replacements: Replacement[]
  unreplaced: GroundingDrop[]
} {
  const ordered = by_row(drops)
  const replacements = ordered
    .slice(0, new_prompts.length)
    .map((d, i) => ({ row: d.scenario_index, scenario: new_prompts[i] }))
  const merged = [...prompts]
  for (const r of replacements) merged[r.row] = r.scenario
  return {
    prompts: merged,
    replacements,
    unreplaced: ordered.slice(replacements.length),
  }
}

// Places the generated replacement cases on their plan rows. The generate
// request saw only the replacements, so each case's scenario_index points
// into that request; a replacement with no case becomes a drop.
export function place_replacement_cases(
  cases: SyntheticUserCaseWire[],
  replacements: Replacement[],
): { cases: SyntheticUserCaseWire[]; missing: GroundingDrop[] } {
  const placed: SyntheticUserCaseWire[] = []
  const covered = new Set<number>()
  cases.forEach((c, position) => {
    const replacement = replacements[c.scenario_index ?? position]
    // A second case for the same scenario would take a row twice.
    if (!replacement || covered.has(replacement.row)) return
    covered.add(replacement.row)
    placed.push({ ...c, scenario_index: replacement.row })
  })
  const missing = replacements
    .filter((r) => !covered.has(r.row))
    .map((r) => ({
      scenario_index: r.row,
      scenario: r.scenario,
      drop_detail: SIMULATED_USER_MISSING_DETAIL,
    }))
  return { cases: by_row(placed), missing }
}

// Replace's paid first half: a plan with one new scenario per drop, then a
// simulated user for each. Every request gets the same signal and runs only
// while it hasn't aborted, so a Back during any step stops the rest. Null when
// a request failed (it reports why itself); an abort throws an AbortError.
export async function plan_and_generate_replacements(args: {
  prompts: string[]
  drops: GroundingDrop[]
  signal: AbortSignal
  guidance: (signal: AbortSignal) => Promise<string>
  request_plan: (
    guidance: string,
    count: number,
    signal: AbortSignal,
  ) => Promise<{ prompts: string[] } | null>
  generate: (
    scenarios: string[],
    signal: AbortSignal,
  ) => Promise<SyntheticUserCaseWire[] | null>
  on_generating: () => void
}): Promise<{
  merged: ReturnType<typeof plan_replacements>
  placed: ReturnType<typeof place_replacement_cases>
} | null> {
  const { signal, drops } = args
  throw_if_aborted(signal)
  const guidance = await unless_aborted(signal, args.guidance(signal))
  const planned = await unless_aborted(
    signal,
    args.request_plan(guidance, drops.length, signal),
  )
  if (!planned) return null
  const merged = plan_replacements(args.prompts, drops, planned.prompts)
  args.on_generating()
  const generated = await unless_aborted(
    signal,
    args.generate(
      merged.replacements.map((r) => r.scenario),
      signal,
    ),
  )
  if (generated === null) return null
  return {
    merged,
    placed: place_replacement_cases(generated, merged.replacements),
  }
}

// A merged case list: the kept cases, less any on a replaced row, plus the
// added ones, in plan order. A kept case without a scenario_index sits at
// its position, as the drive reads it.
export function merge_cases(
  kept: SyntheticUserCaseWire[],
  replaced_rows: Set<number>,
  added: SyntheticUserCaseWire[],
): SyntheticUserCaseWire[] {
  const resolved = kept
    .map((c, position) => ({
      ...c,
      scenario_index: c.scenario_index ?? position,
    }))
    .filter((c) => !replaced_rows.has(c.scenario_index))
  return by_row([...resolved, ...added])
}

// A replacement plan committed to the page: the merged plan, the drops it
// still carries, and the new cases that were sent for grounding.
export type CommittedReplacement = {
  prompts: string[]
  unreplaced: GroundingDrop[]
  missing: GroundingDrop[]
  sent_for_grounding: SyntheticUserCaseWire[]
}

// The drop reason for a replacement whose grounding failed or was stopped.
export function unchecked_detail(error: string | null): string {
  return error
    ? `Kiln couldn't check this case against your OpenEnv server: ${error}`
    : "Kiln stopped before checking this case against your OpenEnv server."
}

// The dropped-cases screen after Replace stopped part-way, by a failure
// (error is its message) or the user (error is null). Before the merged plan
// was committed, the screen comes back as it was. After, it shows the merged
// plan: the kept cases stay grounded, so Continue drives them without
// grounding them again, and each new case that wasn't checked is a drop.
export function interrupted_replacement(args: {
  kept: SyntheticUserCaseWire[]
  drops: GroundingDrop[]
  committed: CommittedReplacement | null
  error: string | null
}): {
  grounded: SyntheticUserCaseWire[]
  drops: GroundingDrop[]
  replace_error: string | null
} {
  const { kept, committed, error } = args
  if (!committed)
    return { grounded: kept, drops: args.drops, replace_error: error }
  const unchecked = committed.sent_for_grounding.map((c, position) => {
    const row = c.scenario_index ?? position
    return {
      scenario_index: row,
      scenario: committed.prompts[row] ?? c.seed_prompt,
      drop_detail: unchecked_detail(error),
    }
  })
  return {
    grounded: kept,
    drops: merge_drops(committed.unreplaced, committed.missing, unchecked),
    replace_error: error,
  }
}

// Drops from several sources as one list, in plan order.
export function merge_drops(...lists: GroundingDrop[][]): GroundingDrop[] {
  return by_row(lists.flat())
}

function by_row<T extends { scenario_index?: number | null }>(items: T[]): T[] {
  return [...items].sort(
    (a, b) => (a.scenario_index ?? 0) - (b.scenario_index ?? 0),
  )
}
