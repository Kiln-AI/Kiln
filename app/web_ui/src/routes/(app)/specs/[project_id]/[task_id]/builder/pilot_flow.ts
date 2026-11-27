// Generation Settings' "Pilot First" box (multi-turn). When it is on, the
// build stops after the case writer, before any grounding call, so the owner
// reads every first message and can Continue or Refine the plan. When it is
// off, the build runs exactly as it did before the box existed: the steps
// below call the same functions in the same order and add no await.

export type FirstMessagesChoice = "continue" | "refine"

// One pending owner choice. wait() resolves when choose() is called; an abort
// of the signal rejects with the AbortError the drive's catch already handles,
// so Back or leaving the page mid-wait cancels the build like any other step.
export type OwnerChoiceGate<T> = {
  wait: (signal: AbortSignal) => Promise<T>
  choose: (choice: T) => void
  pending: () => boolean
}

export function owner_choice_gate<T>(): OwnerChoiceGate<T> {
  let resolve_current: ((choice: T) => void) | null = null
  return {
    wait(signal: AbortSignal): Promise<T> {
      return new Promise<T>((resolve, reject) => {
        const abort = () => {
          resolve_current = null
          reject(new DOMException("The build was cancelled.", "AbortError"))
        }
        if (signal.aborted) {
          abort()
          return
        }
        signal.addEventListener("abort", abort, { once: true })
        resolve_current = (choice: T) => {
          signal.removeEventListener("abort", abort)
          resolve_current = null
          resolve(choice)
        }
      })
    },
    choose(choice: T) {
      resolve_current?.(choice)
    },
    pending() {
      return resolve_current !== null
    },
  }
}

// The write → (owner reads the first messages) → ground sequence of one
// build. `write` returns the cases (null after it set its own error);
// `ground` grounds them (or passes them through on a build without an
// OpenEnv server). With pilot_first off, review is never called: the calls
// are write then ground, as before. With it on, a Refine stops the build
// before ground runs and returns null.
export async function write_review_ground<C, R>(steps: {
  pilot_first: boolean
  write: () => Promise<C[] | null>
  review: (cases: C[]) => Promise<FirstMessagesChoice>
  ground: (cases: C[]) => Promise<R | null>
}): Promise<R | null> {
  const cases = await steps.write()
  if (cases === null) return null
  if (steps.pilot_first && (await steps.review(cases)) !== "continue") {
    return null
  }
  return steps.ground(cases)
}

// The first messages the owner reads, in plan order.
export function first_messages(
  cases: { seed_prompt: string; scenario_index?: number | null }[],
): { key: string; label: string; text: string }[] {
  return cases.map((c, position) => {
    const row = c.scenario_index ?? position
    return {
      key: `${position}:${row}`,
      label: `Plan row ${row + 1}`,
      text: c.seed_prompt,
    }
  })
}

// ── The pilot of 12 ───────────────────────────────────────────────────────
//
// With Pilot First on, Continue on the first messages grounds, drives and
// judges only a pilot of PILOT_CASES cases, spread over the plan. The eval
// check panel then shows for those cases, and its Continue grounds, drives
// and judges the rest into the same batch, keeping the pilot's results.

export const PILOT_CASES = 12

// The positions of the pilot in a list of n cases in plan order: spread
// evenly from the first row on, the same every time. Empty when the whole
// list is no bigger than a pilot, so a small build runs as one batch.
export function pilot_positions(
  n: number,
  size: number = PILOT_CASES,
): number[] {
  if (n <= size) return []
  return Array.from({ length: size }, (_, k) => Math.floor((k * n) / size))
}

// Splits the written cases into the pilot and the rest. Each case is stamped
// with its plan row first, so grounding reads the right row for a case that
// is no longer at its plan position.
export function split_pilot<C extends { scenario_index?: number | null }>(
  cases: C[],
  size: number = PILOT_CASES,
): { pilot: C[]; rest: C[] } | null {
  const positions = pilot_positions(cases.length, size)
  if (positions.length === 0) return null
  const stamped = cases.map((c, i) => ({
    ...c,
    scenario_index: c.scenario_index ?? i,
  }))
  const chosen = new Set(positions)
  return {
    pilot: stamped.filter((_, i) => chosen.has(i)),
    rest: stamped.filter((_, i) => !chosen.has(i)),
  }
}

// The pilot that ran, kept until its rest runs or the plan changes. `key`
// holds everything the pilot's cases depend on (plan, spec, grounding
// settings); a rest run with another key starts over.
export type PilotState<C, D> = {
  key: string
  // The pilot's cases as driven (grounded on an OpenEnv build).
  pilot_cases: C[]
  pilot_drops: D[]
  // The written cases not yet grounded or driven.
  rest: C[]
}

// The whole batch for the rest run: the pilot's cases first, in the order
// they ran, then the rest. Kept in that order so the pilot's results keep
// their slots (and their trace ids) when the rest tops the batch off.
export function batch_after_pilot<C>(pilot_cases: C[], rest_cases: C[]): C[] {
  return [...pilot_cases, ...rest_cases]
}

// The current batch, widened to the full batch so the rest run tops it off:
// the pilot's slots keep their results, the rest's slots are empty. Null
// when the current batch is not the pilot (another drive ran since), so the
// caller drives fresh as before.
export function widen_pilot_batch<C, R>(args: {
  batch_items: C[] | null
  built_slots: readonly (R | null)[]
  pilot_cases: C[]
  full_items: C[]
}): { batch_items: C[]; built_slots: (R | null)[] } | null {
  const { batch_items, built_slots, pilot_cases, full_items } = args
  if (batch_items === null) return null
  if (JSON.stringify(batch_items) !== JSON.stringify(pilot_cases)) return null
  if (built_slots.length !== batch_items.length) return null
  if (
    JSON.stringify(full_items.slice(0, pilot_cases.length)) !==
    JSON.stringify(pilot_cases)
  ) {
    return null
  }
  return {
    batch_items: full_items,
    built_slots: [
      ...built_slots,
      ...new Array(full_items.length - built_slots.length).fill(null),
    ],
  }
}
