<script context="module" lang="ts">
  import {
    MATCH_LABELS,
    MIN_MATCHED_N,
    SHAPE_RATIO_LIMIT,
    undetectable_difference_pp,
    type MatchPredicate,
  } from "$lib/utils/evolution/run_matching"

  /** One eval's share of the basis, already named for the reader. */
  export interface BasisEval {
    evalId: string
    name: string
    /** Items the comparison is over */
    matched: number
    /** Items every basis config ran, before any shape filtering */
    shared: number
    /** Rows the basis configs have for this eval, smallest and largest */
    universe_min: number
    universe_max: number
  }

  export interface BasisError {
    label: string
    message: string
  }

  function range_phrase(min: number, max: number): string {
    return min === max ? `${min}` : `${min}–${max}`
  }

  function list_phrase(items: string[], limit = 3): string {
    if (items.length <= limit) return items.join(", ")
    return `${items.slice(0, limit).join(", ")} and ${items.length - limit} more`
  }

  /**
   * The one line that states what the numbers on this page are over.
   *
   * Always rendered, including at the default predicate: an invisible N is the
   * complaint this whole feature exists to answer, and "n varies by eval and
   * config" is exactly the fact that makes a pooled comparison worth
   * questioning.
   */
  export function basis_line(
    applied: MatchPredicate,
    requested: MatchPredicate,
    basis_count: number,
    evals: BasisEval[],
    n_range: { min: number; max: number } | null,
  ): string {
    if (applied === "all") {
      // A predicate was asked for but cannot mean anything yet. Said rather
      // than silently ignored - the picker still shows the reader's choice.
      if (requested !== "all") {
        return `All runs · ${MATCH_LABELS[requested]} needs at least 2 pinned configs`
      }
      if (!n_range) {
        return "All runs · no scores yet on the pinned configs"
      }
      return (
        `All runs · n=${range_phrase(n_range.min, n_range.max)} ` +
        `by eval and config — configs are not compared on the same conversations`
      )
    }

    const scored = evals.filter((entry) => entry.universe_max > 0)
    const shape =
      applied === "shared"
        ? ""
        : ` · ${MATCH_LABELS[applied].toLowerCase()} (within ${SHAPE_RATIO_LIMIT}×)`
    const configs = `${basis_count} ${basis_count === 1 ? "config" : "configs"}`

    if (scored.length === 0) {
      return `${MATCH_LABELS.shared}${shape} · ${configs} · no runs to match on`
    }

    const matched = range_phrase(
      Math.min(...scored.map((entry) => entry.matched)),
      Math.max(...scored.map((entry) => entry.matched)),
    )
    const universe = range_phrase(
      Math.min(...scored.map((entry) => entry.universe_min)),
      Math.max(...scored.map((entry) => entry.universe_max)),
    )
    // "of" is what makes a predicate change NOTICEABLE: it states what
    // tightening the basis cost, in the same breath as what it bought.
    return (
      `${MATCH_LABELS.shared}${shape} · ${configs} · ` +
      `${matched} matched conversations per eval (of ${universe})`
    )
  }

  /**
   * The caveats that have to travel with whichever basis is active.
   *
   * Both of these are about the SAME number - the cost axis - reading
   * differently depending on the basis, which is not something a reader can be
   * expected to derive from a predicate name.
   */
  export function basis_notes(applied: MatchPredicate): string[] {
    if (applied === "all") {
      return [
        "Cost and latency here are over whatever runs each config has, so a gap between two configs includes however differently they wandered, not just what they charge.",
      ]
    }
    const notes = [
      // The matched rollup counts a CONVERSATION once; the server's usage
      // rollup counts it once per eval that scored it. With trace reuse those
      // are different weightings of the same runs, and the difference is
      // visible the moment a predicate is switched on.
      "Cost and latency are re-averaged over these conversations, each counted once — the usage rollup counts a conversation once per eval that scored it, so these figures can move even when N barely does.",
    ]
    if (applied === "length") {
      notes.push(
        "Length matching holds the workload roughly equal, so a cost gap here reads as price per token rather than as work done.",
      )
    }
    if (applied === "tools" || applied === "length") {
      notes.push(
        "This is a lens, not a control: it keeps the conversations where neither config wandered, which is itself an outcome of how they ran.",
      )
    }
    return notes
  }

  /** What the predicate could not do, and why - never left to be inferred. */
  export function basis_diagnostics(
    applied: MatchPredicate,
    evals: BasisEval[],
    missing_shape_labels: string[],
    tool_source_available: boolean,
    errors: BasisError[],
  ): string[] {
    const lines: string[] = []

    for (const error of errors) {
      lines.push(
        `Couldn't load runs for ${error.label}: ${error.message} — it is left out of the basis rather than pooled in.`,
      )
    }

    if (applied === "all") {
      return lines
    }

    const empty = evals
      .filter((entry) => entry.universe_max > 0 && entry.matched === 0)
      .map((entry) => entry.name)
    if (empty.length > 0) {
      lines.push(
        `No matched conversations on ${list_phrase(empty)} — ${
          empty.length === 1 ? "that eval's" : "those evals'"
        } cells are empty for this basis.`,
      )
    }

    if (applied === "tools" && !tool_source_available) {
      lines.push(
        `No eval on this task records tool calls, so ${MATCH_LABELS.tools} has nothing to match on.`,
      )
    } else if (missing_shape_labels.length > 0) {
      const what = applied === "tools" ? "tool-call metrics" : "token counts"
      lines.push(
        `${list_phrase(missing_shape_labels)} ${
          missing_shape_labels.length === 1 ? "has" : "have"
        } no ${what} — ${MATCH_LABELS[applied]} is unavailable for this basis.`,
      )
    }

    return lines
  }

  export interface SmallSetWarning {
    text: string
    tooltip: string
  }

  /**
   * The whole overfitting guardrail: one chip, nothing blocked, nothing
   * recolored. The resolution figure is DERIVED from the actual n rather than
   * quoted, so it cannot drift from the sample it describes.
   */
  export function small_set_warning(
    applied: MatchPredicate,
    evals: BasisEval[],
  ): SmallSetWarning | null {
    if (applied === "all") return null
    const small = evals
      .filter(
        (entry) => entry.universe_max > 0 && entry.matched < MIN_MATCHED_N,
      )
      .sort((a, b) => a.matched - b.matched)
    const worst = small[0]
    if (!worst) return null

    const pp = undetectable_difference_pp(worst.matched)
    const resolution =
      pp === null
        ? "nothing can be read off it"
        : `differences under ~${pp}pp are undetectable here`
    const others =
      small.length > 1
        ? ` (and ${small.length - 1} other ${small.length === 2 ? "eval" : "evals"})`
        : ""
    return {
      text: `Small matched set: “${worst.name}” n=${worst.matched}${others} — ${resolution}`,
      tooltip:
        "A matched set this small can be shaped by a handful of conversations. " +
        "Reading a winner off it is fitting to whichever runs the predicate happened to leave, " +
        "not to a difference between the configs.",
    }
  }
</script>

<script lang="ts">
  // The single place the page states what its numbers are over.
  //
  // It sits between the legend and the charts because it governs all of them:
  // the radar, the bars, the parallel view, the price/latency scatter and both
  // tables are one comparison drawn several ways, and the basis is a property
  // of the comparison rather than of any one picture.
  //
  // It is rendered at every predicate, including the default. The page's core
  // complaint was that N is invisible and the pooling is silent; a banner that
  // only appeared once you had already fixed the problem would say nothing to
  // the reader who has not.
  export let applied: MatchPredicate = "all"
  export let requested: MatchPredicate = "all"
  export let basis_count: number = 0
  export let evals: BasisEval[] = []
  /** n across (eval, config) cells at the default predicate; null when none */
  export let n_range: { min: number; max: number } | null = null
  /** Config labels with no shape value at all for the active predicate */
  export let missing_shape_labels: string[] = []
  export let tool_source_available: boolean = true
  export let errors: BasisError[] = []
  /** True while the per-run indexes a predicate needs are still arriving */
  export let loading: boolean = false

  $: line = basis_line(applied, requested, basis_count, evals, n_range)
  $: notes = basis_notes(applied)
  $: diagnostics = basis_diagnostics(
    applied,
    evals,
    missing_shape_labels,
    tool_source_available,
    errors,
  )
  $: warning = small_set_warning(applied, evals)
</script>

<div
  class="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2"
  data-testid="comparison-basis"
>
  <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
    <span class="text-xs text-gray-900" data-testid="basis-line">
      {#if loading}
        Matching runs…
      {:else}
        {line}
      {/if}
    </span>
    {#if warning && !loading}
      <span
        class="text-[11px] rounded-full px-2 py-0.5 bg-amber-50 text-amber-800 border border-amber-200"
        title={warning.tooltip}
        data-testid="basis-warning"
      >
        ⚠ {warning.text}
      </span>
    {/if}
    {#if loading}
      <span class="loading loading-spinner loading-xs text-gray-400"></span>
    {/if}
  </div>
  {#if !loading}
    {#each notes as note}
      <div class="text-[11px] text-gray-500 mt-1" data-testid="basis-note">
        {note}
      </div>
    {/each}
    {#each diagnostics as diagnostic}
      <div
        class="text-[11px] text-gray-500 mt-1"
        data-testid="basis-diagnostic"
      >
        {diagnostic}
      </div>
    {/each}
  {/if}
</div>
