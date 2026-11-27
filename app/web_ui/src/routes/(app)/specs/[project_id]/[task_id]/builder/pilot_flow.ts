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
