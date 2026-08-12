import { get, writable } from "svelte/store"

/**
 * Which run configs the reader has switched OFF on the compare charts.
 *
 * This is page state, not chart state, and that is the whole point of it
 * living here. Compare V2 draws the same pinned set three times - the quality
 * radar, the performance bars and the parallel-coordinates view of the same
 * quality scores - and each of those used to carry its own echarts legend,
 * keyed by DISPLAY NAME and toggled independently. Switching a config off to
 * read the radar left it drawn on the two charts underneath, which is the
 * opposite of what "hide this one" means when the three plots are one
 * comparison seen three ways.
 *
 * HIDDEN-set semantics rather than a visible set, deliberately: the empty set
 * means everything is visible, so a newly pinned config appears without anyone
 * having to write to this store first. A visible-set would need every pin to
 * register itself, and anything that failed to would silently vanish from all
 * three charts at once.
 *
 * Ids, not names. Two run configs can carry the same display name - the name
 * is optional and falls back to the model - and echarts' name-keyed legend
 * would toggle both of them together.
 */
export const hidden_run_config_ids = writable<Set<string>>(new Set<string>())

/** Switch one run config off, or back on if it is already off. */
export function toggle_run_config(id: string): void {
  hidden_run_config_ids.update((hidden) => {
    // A new Set rather than a mutation: svelte's store contract is identity
    // based, and mutating the existing one notifies nobody.
    const next = new Set(hidden)
    if (!next.delete(id)) {
      next.add(id)
    }
    return next
  })
}

/**
 * Forget anything hidden that is no longer pinned.
 *
 * Without this, unpinning a hidden config and pinning it again brings it back
 * INVISIBLE, for a reason nothing on screen explains - the legend chip is
 * there, dimmed, and the reader has no memory of switching it off. The rule
 * the parallel chart already applied to its own local legend state, hoisted to
 * the one place that now owns it.
 *
 * A no-op when nothing has to be dropped, so a reactive statement wired to the
 * pinned list cannot churn the store on every unrelated redraw.
 */
export function reconcile_visibility(pinned_ids: string[]): void {
  const pinned = new Set(pinned_ids)
  const current = get(hidden_run_config_ids)
  const kept = new Set<string>()
  for (const id of current) {
    if (pinned.has(id)) {
      kept.add(id)
    }
  }
  if (kept.size !== current.size) {
    hidden_run_config_ids.set(kept)
  }
}

/**
 * The pinned configs a chart should actually draw, in pinned order.
 *
 * Hiding is subtraction at the SOURCE: a hidden config never reaches a chart,
 * rather than reaching it and being suppressed there. That is what keeps the
 * three charts in step without any of them knowing this store exists.
 */
export function visible_ids(
  pinned_ids: string[],
  hidden: Set<string>,
): string[] {
  return pinned_ids.filter((id) => !hidden.has(id))
}

/** Everything visible again. Mostly for tests and for tearing down state. */
export function reset_visibility(): void {
  hidden_run_config_ids.set(new Set<string>())
}
