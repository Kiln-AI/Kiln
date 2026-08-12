<script context="module" lang="ts">
  import {
    MATCH_LABELS,
    MIN_MATCHED_N,
    SHAPE_RATIO_LIMIT,
    undetectable_difference_pp,
    type MatchFallback,
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
    /** Items at least one basis config ran — the denominator */
    universe: number
    /** What the requested shape predicate would have kept; null if none asked */
    shape_matched: number | null
    /** Shared items with no usable shape value, or one from another run */
    missing_shape: number
    /** A metrics eval, which runs over its own much larger item universe */
    is_metric: boolean
  }

  export interface BasisError {
    label: string
    message: string
  }

  /** One eval's cheapest way out of a matched set too small to read. */
  export interface BasisRecovery {
    /** The eval, named */
    name: string
    /** The config to drop, named */
    config: string
    from: number
    to: number
  }

  function range_phrase(min: number, max: number): string {
    return min === max ? `${min}` : `${min}–${max}`
  }

  function list_phrase(items: string[], limit = 3): string {
    if (items.length <= limit) return items.join(", ")
    return `${items.slice(0, limit).join(", ")} and ${items.length - limit} more`
  }

  function count_phrase(n: number, noun: string): string {
    return `${n} ${noun}${n === 1 ? "" : "s"}`
  }

  /**
   * What one lane of evals kept, as a fraction of what it had.
   *
   * A ratio and not a range, because a range is not a denominator: "22–25
   * matched (of 25–74)" pairs the smallest matched count on one eval with the
   * largest universe on another, and 22 of 74 is a sentence about no eval that
   * exists. Summing per eval - each eval's matched over its OWN union - is a
   * number every part of which came from the same place, and the per-eval
   * spread rides along beside it rather than being folded in.
   */
  function retention_phrase(evals: BasisEval[]): string {
    const scored = evals.filter((entry) => entry.universe > 0)
    if (scored.length === 0) return ""
    const kept = scored.reduce((total, entry) => total + entry.matched, 0)
    const universe = scored.reduce((total, entry) => total + entry.universe, 0)
    if (scored.length === 1) {
      return `${kept}/${universe} conversations on “${scored[0].name}”`
    }
    // Every eval's own ratio while they fit; past that the two ends of the
    // spread, which is what a reader scanning a line of eight would take from
    // it anyway.
    const share = (entry: BasisEval) => entry.matched / entry.universe
    const worst = scored.reduce((a, b) => (share(a) <= share(b) ? a : b))
    const best = scored.reduce((a, b) => (share(a) >= share(b) ? a : b))
    const spread =
      scored.length <= 3
        ? scored
            .map((entry) => `${entry.matched}/${entry.universe}`)
            .join(" · ")
        : `${worst.matched}/${worst.universe} to ${best.matched}/${best.universe} each`
    return `kept ${kept}/${universe} across ${count_phrase(scored.length, "graded eval")} (${spread})`
  }

  /**
   * The one line that states what the numbers on this page are over.
   *
   * Always rendered, including at the default predicate: an invisible N is the
   * complaint this whole feature exists to answer, and "n varies by eval and
   * config" is exactly the fact that makes a pooled comparison worth
   * questioning.
   *
   * The measurement lane is stated SEPARATELY rather than pooled into the
   * graded retention. A metrics eval scores every conversation on the task
   * (175 items where the graded evals hold 25 each), so folding it in produces
   * a fraction dominated by a lane nobody is reading criteria off.
   */
  export function basis_line(
    applied: MatchPredicate,
    requested: MatchPredicate,
    basis_count: number,
    evals: BasisEval[],
    n_range: { min: number; max: number } | null,
  ): string {
    if (applied === "all") {
      const n = n_range
        ? `n=${range_phrase(n_range.min, n_range.max)} by eval and config`
        : "no scores yet on the pinned configs"
      if (basis_count < 2) {
        // Matching is the identity on one config, so there is nothing to
        // report unless the reader explicitly picked a shape predicate - the
        // default one arriving here is not a choice anybody made.
        const asked =
          requested === "length" || requested === "tools"
            ? ` — ${MATCH_LABELS[requested]} needs at least 2 pinned configs`
            : ""
        return `${MATCH_LABELS.all} · ${n}${asked}`
      }
      // The caveat is about numbers that exist. With none, "these are not the
      // same conversations" would be a claim about nothing.
      if (!n_range) {
        return `${MATCH_LABELS.all} · ${n}`
      }
      return (
        `${MATCH_LABELS.all} · ${n} — configs are not compared on the ` +
        `same conversations`
      )
    }

    const shape =
      applied === "shared"
        ? ""
        : ` · ${MATCH_LABELS[applied].toLowerCase()} (within ${SHAPE_RATIO_LIMIT}×)`
    const configs = count_phrase(basis_count, "config")

    const graded = evals.filter((entry) => !entry.is_metric)
    const metrics = evals.filter(
      (entry) => entry.is_metric && entry.universe > 0,
    )
    const parts = [`${MATCH_LABELS.shared}${shape}`, configs]

    const retention = retention_phrase(graded)
    if (retention) parts.push(retention)
    for (const entry of metrics) {
      parts.push(`${entry.name}: ${entry.matched}/${entry.universe}`)
    }
    if (!retention && metrics.length === 0) {
      parts.push("no runs to match on")
    }
    return parts.join(" · ")
  }

  /**
   * Why a shape predicate is not the one being shown, and what to do instead.
   *
   * Both exits are measurable rather than advisory: the retention figure is
   * the one the predicate actually produced, and the recovery lines name a
   * config and the n that dropping it recovers. "Try fewer configs" on its own
   * is a shrug.
   */
  export function unavailable_lens_lines(
    fallback: MatchFallback | null,
    requested: MatchPredicate,
    basis_count: number,
    evals: BasisEval[],
    recovery: BasisRecovery[],
  ): string[] {
    if (fallback !== "shape_too_thin") return []
    const graded = evals.filter((entry) => !entry.is_metric && entry.shared > 0)
    const shared_total = graded.reduce((total, e) => total + e.shared, 0)
    const shaped_total = graded.reduce(
      (total, e) => total + (e.shape_matched ?? 0),
      0,
    )
    const percent =
      shared_total > 0 ? Math.round((shaped_total / shared_total) * 100) : 0
    const lines = [
      `${MATCH_LABELS[requested]} is unavailable at this basis: across ` +
        `${count_phrase(basis_count, "mutually-matched config")} it keeps about ` +
        `${percent}% of the shared conversations, and this lens is built for ` +
        `2–3. Showing ${MATCH_LABELS.shared.toLowerCase()} instead.`,
    ]
    for (const hint of recovery.slice(0, 2)) {
      lines.push(
        `Dropping ${hint.config} takes “${hint.name}” from ${hint.from} to ` +
          `${hint.to} matched conversations.`,
      )
    }
    lines.push(
      "Or compare 2–3 configs, which is what these predicates hold up at.",
    )
    return lines
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
    requested: MatchPredicate,
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

    // Named individually rather than counted, and up to four of them: "and 5
    // other evals" is where four evals with NOTHING matched were hiding, and
    // an eval with no cells at all is a different fact from one with few.
    const empty = evals
      .filter((entry) => entry.universe > 0 && entry.matched === 0)
      .map((entry) => `“${entry.name}”`)
    if (empty.length > 0) {
      lines.push(
        `No matched conversations at all on ${list_phrase(empty, 4)} — ${
          empty.length === 1 ? "that eval's" : "those evals'"
        } cells are empty for this basis.`,
      )
    }

    // Where a shape value was missing rather than out of tolerance. Per eval,
    // because "17 of 17" is a fact about Write Correctness and about nothing
    // else - it is the whole reason that eval went blank, and a count pooled
    // across evals would read as bad luck spread thinly.
    if (requested === "length" || requested === "tools") {
      const what =
        requested === "tools"
          ? "lack a same-run tool-call record"
          : "have no recorded token count"
      const missing = evals
        .filter((entry) => entry.missing_shape > 0)
        .sort((a, b) => b.missing_shape - a.missing_shape)
      for (const entry of missing.slice(0, 3)) {
        lines.push(
          `“${entry.name}”: ${entry.missing_shape} of ${entry.shared} shared conversations ${what}.`,
        )
      }
      if (missing.length > 3) {
        lines.push(
          `${missing.length - 3} other ${
            missing.length - 3 === 1 ? "eval" : "evals"
          } lost conversations the same way.`,
        )
      }
    }

    if (requested === "tools" && !tool_source_available) {
      lines.push(
        `No eval on this task records tool calls, so ${MATCH_LABELS.tools} has nothing to match on.`,
      )
    } else if (missing_shape_labels.length > 0) {
      const what = requested === "tools" ? "tool-call metrics" : "token counts"
      lines.push(
        `${list_phrase(missing_shape_labels)} ${
          missing_shape_labels.length === 1 ? "has" : "have"
        } no ${what} — ${MATCH_LABELS[requested]} is unavailable for this basis.`,
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
   *
   * SMALL, not empty. An eval with nothing matched has no interval to be too
   * wide - it has no cells - and it belongs in the diagnostics that name it,
   * where the four evals that used to hide inside "(and 5 other evals)" are
   * each stated. Mixing the two put a resolution figure on a sample of zero
   * and buried the more serious fact behind the less serious one.
   */
  export function small_set_warning(
    applied: MatchPredicate,
    evals: BasisEval[],
  ): SmallSetWarning | null {
    if (applied === "all") return null
    const small = evals
      .filter((entry) => entry.matched > 0 && entry.matched < MIN_MATCHED_N)
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
  /** Why applied is not requested, when it is not */
  export let fallback: MatchFallback | null = null
  export let basis_count: number = 0
  export let evals: BasisEval[] = []
  /** n across (eval, config) cells at the default predicate; null when none */
  export let n_range: { min: number; max: number } | null = null
  /** Config labels with no shape value at all for the active predicate */
  export let missing_shape_labels: string[] = []
  export let tool_source_available: boolean = true
  export let errors: BasisError[] = []
  /** What dropping one config would recover, per eval, worst first */
  export let recovery: BasisRecovery[] = []
  /** True while the per-run indexes a predicate needs are still arriving */
  export let loading: boolean = false

  $: line = basis_line(applied, requested, basis_count, evals, n_range)
  $: notes = basis_notes(applied)
  // The unavailable-lens explanation leads the diagnostics: it is the reason
  // the rest of them read the way they do.
  $: diagnostics = [
    ...unavailable_lens_lines(
      fallback,
      requested,
      basis_count,
      evals,
      recovery,
    ),
    ...basis_diagnostics(
      applied,
      requested,
      evals,
      missing_shape_labels,
      tool_source_available,
      errors,
    ),
  ]
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
