<script context="module" lang="ts">
  import type { ScoreKeyMeta } from "$lib/utils/evolution/score_lens"

  // Exported so the page can label hidden usage rows without duplicating the
  // list (and validate `?hidden_usage=` against it).
  export const USAGE_ROWS = [
    { key: "cost", label: "Mean cost" },
    { key: "tokens", label: "Mean total tokens" },
    { key: "latency", label: "Mean latency" },
  ] as const

  export type UsageRowKey = (typeof USAGE_ROWS)[number]["key"]

  // A row is either an eval score key or one of the native usage rollup fields.
  // Both carry their own label rather than deriving one: the two tracks name
  // the same quantity differently on the chart and in the table (see
  // metric_row_info), and that decision belongs to the page that partitions
  // them, not to the renderer.
  export type MatrixScoreRow = {
    kind: "score"
    meta: ScoreKeyMeta
    label: string
    sublabel: string
  }

  export type MatrixUsageRow = {
    kind: "usage"
    key: UsageRowKey
    label: string
    sublabel: string
  }

  export type MatrixRow = MatrixScoreRow | MatrixUsageRow

  /**
   * One family of rows, with the heading it is drawn under.
   *
   * A null label is an ungrouped run, which is what a task with no declared
   * taxonomy produces: the group renders as a plain list with no header, so the
   * table is exactly what it was before grouping existed.
   */
  export type MatrixGroup = {
    key: string
    label: string | null
    rows: MatrixRow[]
  }

  export function matrix_row_key(row: MatrixRow): string {
    return row.kind === "score"
      ? `score::${row.meta.evalId}::${row.meta.scoreKey}`
      : `usage::${row.key}`
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { components } from "$lib/api_schema"
  import type { EvoNode } from "$lib/utils/evolution/graph_assembly"
  import type { LensData } from "$lib/utils/evolution/score_lens"
  import {
    lens_color,
    normalized_score,
    raw_score,
    sample_size,
  } from "$lib/utils/evolution/score_lens"
  import { formatLatency } from "$lib/utils/formatters"
  import { hidden_run_config_ids } from "$lib/utils/evolution/visibility_store"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"

  type RunConfigEvalScoresSummary =
    components["schemas"]["RunConfigEvalScoresSummary"]

  // Pin order is preserved; anything beyond MAX_COLUMNS is not shown.
  export let pinned_nodes: EvoNode[] = []
  export let lens_data: LensData
  export let eval_scores_cache: Record<string, RunConfigEvalScoresSummary> = {}
  export let eval_scores_loading: Record<string, boolean> = {}
  // Rows to draw, already partitioned into a track and grouped into families by
  // the page. Ordering, labelling and which rows the user hid are all settled
  // before they get here.
  export let groups: MatrixGroup[] = []
  // Shown when the track has rows but every one of them is hidden
  export let empty_message: string =
    "Every row is hidden. Use “Hidden” above the table to restore them."
  // Whether the page's chart legend (evolution_legend.svelte) also takes
  // columns out of this table.
  //
  // Off by default, and off at both call sites today, because the charts and
  // the table are read for different things: switching a config off up there
  // is decluttering an image so the remaining shapes can be told apart, and
  // that is not a reason to stop being able to read its numbers. The reader
  // who wants the table to follow the legend flips this to true and gets it
  // for both tracks at once.
  export let respect_visibility: boolean = false
  // Where a usage row's number comes from. Null - the default - is the native
  // per-config rollup in eval_scores_cache, which is what this table has always
  // printed. The page passes a getter instead when a matching predicate is
  // active, so the usage rows are over the same conversations as the score rows
  // above them rather than over every run each config ever had.
  export let get_usage_value:
    | ((run_config_id: string, key: UsageRowKey) => number | null)
    | null = null

  const dispatch = createEventDispatcher<{
    select: string
    inspect: { eval_id: string; run_config_id: string }
    hide_score: string
    hide_usage: string
  }>()

  // The matrix is full page width and scrolls horizontally, so it comfortably
  // holds every pin the page allows.
  const MAX_COLUMNS = 12

  $: shown_nodes = respect_visibility
    ? pinned_nodes.filter((node) => !$hidden_run_config_ids.has(node.id))
    : pinned_nodes
  $: columns = shown_nodes.slice(0, MAX_COLUMNS)
  $: row_count = groups.reduce((total, group) => total + group.rows.length, 0)

  function cell_raw(meta: ScoreKeyMeta, run_config_id: string): number | null {
    return raw_score(lens_data, run_config_id, meta.evalId, meta.scoreKey)
  }

  function cell_color(meta: ScoreKeyMeta, run_config_id: string): string {
    return lens_color(
      normalized_score(lens_data, run_config_id, meta.evalId, meta.scoreKey),
    )
  }

  function delta_vs_first(
    meta: ScoreKeyMeta,
    run_config_id: string,
    first_id: string,
  ): string | null {
    const value = cell_raw(meta, run_config_id)
    const first = cell_raw(meta, first_id)
    if (value === null || first === null) {
      return null
    }
    const delta = value - first
    if (delta === 0) {
      return "±0.00"
    }
    return `${delta > 0 ? "+" : "−"}${Math.abs(delta).toFixed(2)}`
  }

  // Runs behind a cell, printed beside it. A mean over 3 runs and a mean over
  // 300 render identically without it, which is the whole reason a reader
  // cannot tell a pooled comparison from a matched one by looking.
  function cell_n(meta: ScoreKeyMeta, run_config_id: string): number | null {
    return sample_size(lens_data, run_config_id, meta.evalId, meta.scoreKey)
  }

  // Takes the cache and the override as parameters so the template expression
  // re-evaluates when the lazily fetched eval scores (or the matched rollup)
  // arrive.
  function usage_value(
    key: UsageRowKey,
    node_id: string,
    cache: Record<string, RunConfigEvalScoresSummary>,
    override:
      | ((run_config_id: string, key: UsageRowKey) => number | null)
      | null,
  ): string | null {
    if (override) {
      return format_usage(key, override(node_id, key))
    }
    const usage = cache[node_id]?.mean_usage
    if (!usage) {
      return null
    }
    switch (key) {
      case "cost":
        return format_usage(key, usage.mean_cost ?? null)
      case "tokens":
        return format_usage(key, usage.mean_total_tokens ?? null)
      case "latency":
        return format_usage(key, usage.mean_total_llm_latency_ms ?? null)
    }
  }

  function format_usage(key: UsageRowKey, value: number | null): string | null {
    if (value === null || value === undefined) {
      return null
    }
    switch (key) {
      case "cost":
        return `$${value.toFixed(4)}`
      case "tokens":
        return Math.round(value).toLocaleString()
      case "latency":
        return formatLatency(value)
    }
  }
</script>

{#if columns.length > 0}
  <!-- Horizontal scroll (with the score column pinned) is what lets the matrix
       carry 10+ run config columns without squeezing them unreadable. The
       scroll lives on this container, never on the page body. -->
  <div
    class="overflow-x-auto overflow-y-auto max-h-[560px] rounded-lg border border-gray-200 bg-base-100"
  >
    <table class="table table-xs w-max min-w-full">
      <thead>
        <tr>
          <th
            class="sticky top-0 left-0 z-30 bg-base-100 w-44 min-w-[176px] border-r border-gray-200 text-gray-500 font-normal"
          >
            Score
          </th>
          {#each columns as node (node.id)}
            <!-- Bounded so a long run config name truncates instead of
                 stretching its column across the table -->
            <th
              class="sticky top-0 z-10 bg-base-100 font-normal min-w-[150px] max-w-[220px]"
            >
              <button
                type="button"
                class="font-medium text-gray-900 hover:text-primary truncate block w-full text-left"
                title={node.name}
                on:click={() => dispatch("select", node.id)}
              >
                {node.name}
              </button>
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each groups as group (group.key)}
          {#if group.label && group.rows.length > 0}
            <!-- The heading occupies the label column and leaves the data
                 columns empty, rather than spanning them: a colspan across a
                 horizontally scrolling table drifts away from the sticky first
                 column as it scrolls. -->
            <tr class="bg-gray-50">
              <td
                class="sticky left-0 z-10 bg-gray-50 border-r border-gray-200 w-44 min-w-[176px]"
              >
                <div
                  class="text-[10px] font-semibold uppercase tracking-wide text-gray-500 truncate"
                  title={group.label}
                >
                  {group.label}
                  <span class="font-normal text-gray-400">
                    {group.rows.length}
                  </span>
                </div>
              </td>
              {#each columns as node (node.id)}
                <td class="bg-gray-50"></td>
              {/each}
            </tr>
          {/if}
          {#each group.rows as row (matrix_row_key(row))}
            <tr
              class="hover group {row.kind === 'score' ? 'cursor-pointer' : ''}"
              on:click={() =>
                row.kind === "score" &&
                columns[0] &&
                dispatch("inspect", {
                  eval_id: row.meta.evalId,
                  run_config_id: columns[0].id,
                })}
            >
              <td
                class="sticky left-0 z-10 bg-base-100 border-r border-gray-200 w-44 min-w-[176px]"
              >
                <div class="flex items-center gap-1">
                  <div class="min-w-0 flex-1">
                    <div
                      class="text-xs font-medium text-gray-900 truncate"
                      title={row.label}
                    >
                      {row.label}
                    </div>
                    <div
                      class="text-[10px] text-gray-500 truncate"
                      title={row.sublabel}
                    >
                      {row.sublabel}
                    </div>
                  </div>
                  <!-- Hover-revealed so the label column stays quiet at rest -->
                  <button
                    type="button"
                    class="w-3 h-3 flex-none text-gray-400 hover:text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Hide this row and its radar axis"
                    aria-label="Hide {row.label}"
                    on:click|stopPropagation={() =>
                      row.kind === "score"
                        ? dispatch(
                            "hide_score",
                            `${row.meta.evalId}::${row.meta.scoreKey}`,
                          )
                        : dispatch("hide_usage", row.key)}
                  >
                    <CloseIcon />
                  </button>
                </div>
              </td>
              {#each columns as node, column_index (node.id)}
                {#if row.kind === "score"}
                  {@const raw = cell_raw(row.meta, node.id)}
                  {@const n = cell_n(row.meta, node.id)}
                  <td
                    class="cursor-pointer"
                    on:click|stopPropagation={() =>
                      dispatch("inspect", {
                        eval_id: row.meta.evalId,
                        run_config_id: node.id,
                      })}
                  >
                    {#if raw === null}
                      <span class="text-gray-400">—</span>
                    {:else}
                      <span class="inline-flex items-center gap-1.5">
                        <span
                          class="w-2.5 h-2.5 rounded-full flex-none"
                          style="background-color: {cell_color(
                            row.meta,
                            node.id,
                          )}"
                        ></span>
                        <span class="text-xs font-medium text-gray-900">
                          {raw.toFixed(2)}
                        </span>
                        {#if column_index > 0 && columns[0]}
                          {@const delta = delta_vs_first(
                            row.meta,
                            node.id,
                            columns[0].id,
                          )}
                          {#if delta !== null}
                            <span class="text-[10px] text-gray-400">
                              {delta}
                            </span>
                          {/if}
                        {/if}
                        {#if n !== null}
                          <span
                            class="text-[10px] text-gray-400"
                            title="{n} eval {n === 1
                              ? 'run'
                              : 'runs'} behind this mean"
                          >
                            n={n}
                          </span>
                        {/if}
                      </span>
                    {/if}
                  </td>
                {:else}
                  {@const value = usage_value(
                    row.key,
                    node.id,
                    eval_scores_cache,
                    get_usage_value,
                  )}
                  <td>
                    {#if value !== null}
                      <span class="text-xs text-gray-700">{value}</span>
                    {:else if eval_scores_loading[node.id]}
                      <span class="loading loading-spinner loading-xs"></span>
                    {:else}
                      <span class="text-gray-400">—</span>
                    {/if}
                  </td>
                {/if}
              {/each}
            </tr>
          {/each}
        {/each}
        <!-- Hiding every row is a valid (if odd) state, not an error -->
        {#if row_count === 0}
          <tr>
            <td class="text-xs text-gray-500" colspan={columns.length + 1}>
              {empty_message}
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
{/if}
