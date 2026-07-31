<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { components } from "$lib/api_schema"
  import type { Eval } from "$lib/types"
  import { isKilnAgentRunConfig, isMcpRunConfig } from "$lib/types"
  import {
    get_task_composite_id,
    load_available_models,
    load_available_tools,
    load_model_info,
    model_info,
    model_name,
    prompt_name_from_id,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import { agentInfo } from "$lib/agent"
  import FancySelect from "$lib/ui/fancy_select.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { EvoForest, EvoNode } from "$lib/utils/evolution/graph_assembly"
  import {
    build_forest,
    primary_parent_id,
  } from "$lib/utils/evolution/graph_assembly"
  import { layout_forest } from "$lib/utils/evolution/layout"
  import type {
    Lens,
    LensData,
    NodeDisplay,
    ScoreKeyMeta,
  } from "$lib/utils/evolution/score_lens"
  import {
    build_lens_data,
    lens_color,
    lens_key,
    normalized_lens_value,
    parse_lens_key,
    raw_lens_value,
    score_key_id,
    strip_cells,
  } from "$lib/utils/evolution/score_lens"
  import { score_key_label, score_type_max } from "$lib/utils/formatters"
  import type { PromptResponse, ProviderModels } from "$lib/types"
  import { fly } from "svelte/transition"
  import { cubicOut } from "svelte/easing"
  import CompareRadarChart, {
    type ComparisonFeature,
  } from "$lib/components/compare_radar_chart.svelte"
  import CompareMetricsRadarChart from "$lib/components/compare_metrics_radar_chart.svelte"
  import {
    build_metric_axes,
    criterion_key_metas,
    default_metric_axis_keys,
    directionless_key_count,
    known_metric_axis_keys,
    METRIC_FAMILY_LABELS,
    COST_KEY,
    INPUT_TOKENS_KEY,
    LATENCY_KEY,
    OUTPUT_TOKENS_KEY,
    TOTAL_TOKENS_KEY,
    USAGE_KEY_PREFIX,
    type MetricFamily,
  } from "$lib/utils/evolution/metric_axes"
  import EvolutionCanvas from "./evolution_canvas.svelte"
  import NodeDetailPanel from "./node_detail_panel.svelte"
  import UnlinkedSection from "./unlinked_section.svelte"
  import CompareMatrix, { USAGE_ROWS } from "./compare_matrix.svelte"
  import EvalInspector from "./eval_inspector.svelte"
  import FloatingMenu from "$lib/ui/floating_menu.svelte"
  import type { FloatingMenuItem } from "$lib/ui/floating_menu_types"
  import ArtifactPane, { type ArtifactPaneTarget } from "./artifact_pane.svelte"

  type EvalResultsSummaryResponse =
    components["schemas"]["EvalResultsSummaryResponse"]
  type RunConfigEvalScoresSummary =
    components["schemas"]["RunConfigEvalScoresSummary"]

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  agentInfo.set({
    name: "Compare V2",
    description: "Run config lineage, scores, and drill-downs",
  })

  // Data loading state
  let loading_run_configs = true
  let loading_evals = true
  let loading_summary = true
  let load_error: KilnError | null = null
  $: loading = loading_run_configs || loading_evals || loading_summary

  let evals: Eval[] = []
  let summary: EvalResultsSummaryResponse | null = null

  // Lazy per-run-config eval scores (n_used + usage footer in detail panel)
  let eval_scores_cache: Record<string, RunConfigEvalScoresSummary> = {}
  let eval_scores_loading: Record<string, boolean> = {}
  let eval_scores_errors: Record<string, string> = {}

  // UI state (round-tripped through the URL)
  let lens_selected: unknown = "aggregate"
  let selected_id: string | null = null
  let starred_only = false
  let unlinked_expanded = false
  let pins: string[] = []
  // Matrix rows the user hid: score rows keyed `${evalId}::${scoreKey}`, usage
  // rows keyed by their metric. Hiding is a view concern - a hidden score row
  // drops out of the matrix and off the eval-score radar; a hidden usage row
  // only leaves the matrix (the metrics radar has its own axis picker, below).
  // Neither touches the lens aggregate or the node delta strips, which stay
  // full-coverage.
  let hidden_scores: string[] = []
  let hidden_usage: string[] = []
  // Axes on the performance-metrics radar. Null means "follow the default set",
  // which is what almost every visit wants and what keeps the URL clean; a list
  // means the user picked. Kept separate from hidden_scores/hidden_usage on
  // purpose: those hide matrix ROWS, and an axis being off this chart must not
  // take its number out of the table.
  let metric_axis_keys: string[] | null = null

  // Drill-down UI state (not round-tripped)
  let inspector: {
    eval_id: string
    eval_config_id: string
    run_config_id: string
    eval_name: string
    run_config_name: string | null
  } | null = null
  let pane_target: ArtifactPaneTarget | null = null

  // The compare matrix is full width and scrolls horizontally, so the compare
  // set is no longer capped by how many columns fit on screen.
  const MAX_PINS = 12
  // Below this many radar-able axes echarts has no shape to draw, and the
  // chart component renders nothing at all - the page shows a hint instead.
  const MIN_RADAR_AXES = 3

  // Track if we're initializing from URL to avoid updating URL during load
  let isInitializing = true

  let canvas: EvolutionCanvas | null = null

  $: lens = parse_lens_key(
    typeof lens_selected === "string" ? lens_selected : null,
  ) as Lens

  function initializeFromURL() {
    const urlParams = new URLSearchParams($page.url.search)
    const urlLens = urlParams.get("lens")
    if (urlLens) {
      lens_selected = urlLens
    }
    const urlSel = urlParams.get("sel")
    if (urlSel) {
      selected_id = urlSel
    }
    const urlPins = urlParams.get("pins")
    if (urlPins) {
      pins = urlPins.split(",").filter((id) => id.length > 0)
    }
    starred_only = urlParams.get("starred") === "1"
    unlinked_expanded = urlParams.get("unlinked") === "1"

    // Hidden rows restore before data loads - they are just keys. Deduped, and
    // usage keys checked against the known metrics, in case of a hand-edited URL.
    const urlHiddenScores = urlParams.get("hidden_scores")
    if (urlHiddenScores) {
      hidden_scores = [
        ...new Set(
          urlHiddenScores
            .split(",")
            .map((key) => key.trim())
            .filter((key) => key.length > 0),
        ),
      ]
    }
    const urlHiddenUsage = urlParams.get("hidden_usage")
    if (urlHiddenUsage) {
      const known_usage_keys = new Set<string>(USAGE_ROWS.map((row) => row.key))
      hidden_usage = [
        ...new Set(
          urlHiddenUsage
            .split(",")
            .map((key) => key.trim())
            .filter((key) => known_usage_keys.has(key)),
        ),
      ]
    }
    // Present-but-empty is a legal state ("no metric axes"), so the test is
    // against null rather than truthiness. Unknown keys are dropped once the
    // score keys are known, in validateStateFromURL.
    const urlMetrics = urlParams.get("metrics")
    if (urlMetrics !== null) {
      metric_axis_keys = [
        ...new Set(
          urlMetrics
            .split(",")
            .map((key) => key.trim())
            .filter((key) => key.length > 0),
        ),
      ]
    }
  }

  // After data loads, drop URL state that doesn't resolve against it
  function validateStateFromURL() {
    if (selected_id && !forest.nodes.has(selected_id)) {
      selected_id = null
    }
    pins = pins.filter((id) => forest.nodes.has(id)).slice(0, MAX_PINS)
    // Drop hidden score keys that no longer exist, so a stale URL can't leave a
    // row invisible with no way to restore it.
    const known_score_keys = new Set(
      lens_data.keyMetas.map((meta) =>
        score_key_id(meta.evalId, meta.scoreKey),
      ),
    )
    hidden_scores = hidden_scores.filter((key) => known_score_keys.has(key))
    // Same for the metric axes: a stale URL must not leave the chart asking for
    // an axis that no longer exists. Checked against every key that could be an
    // axis rather than the deduplicated set, since which of two sources for a
    // quantity wins depends on usage that has not been fetched yet.
    if (metric_axis_keys !== null) {
      const known_metric_keys = known_metric_axis_keys(lens_data.keyMetas)
      metric_axis_keys = metric_axis_keys.filter((key) =>
        known_metric_keys.has(key),
      )
    }
    // Note: the lens is validated against ALL score keys, not the visible ones -
    // a hidden row's key stays a legal lens.
    if (
      lens.kind === "single" &&
      !lens_data.keyMetas.some(
        (meta) =>
          lens.kind === "single" &&
          meta.evalId === lens.evalId &&
          meta.scoreKey === lens.scoreKey,
      )
    ) {
      lens_selected = "aggregate"
    }
  }

  function updateURL() {
    if (isInitializing) {
      return
    }
    const urlParams = new URLSearchParams($page.url.search)

    const serialized_lens = lens_key(lens)
    if (serialized_lens !== "aggregate") {
      urlParams.set("lens", serialized_lens)
    } else {
      urlParams.delete("lens")
    }
    if (selected_id) {
      urlParams.set("sel", selected_id)
    } else {
      urlParams.delete("sel")
    }
    if (pins.length > 0) {
      urlParams.set("pins", pins.join(","))
    } else {
      urlParams.delete("pins")
    }
    if (starred_only) {
      urlParams.set("starred", "1")
    } else {
      urlParams.delete("starred")
    }
    if (unlinked_expanded) {
      urlParams.set("unlinked", "1")
    } else {
      urlParams.delete("unlinked")
    }
    if (hidden_scores.length > 0) {
      urlParams.set("hidden_scores", hidden_scores.join(","))
    } else {
      urlParams.delete("hidden_scores")
    }
    if (hidden_usage.length > 0) {
      urlParams.set("hidden_usage", hidden_usage.join(","))
    } else {
      urlParams.delete("hidden_usage")
    }
    // Only written once the user has picked; the default set stays implicit so
    // it can change without stale URLs pinning an old one.
    if (metric_axis_keys !== null) {
      urlParams.set("metrics", metric_axis_keys.join(","))
    } else {
      urlParams.delete("metrics")
    }

    // Replace state: this only records existing UI state in the URL.
    // noScroll/keepFocus so selecting a node doesn't jump the page.
    const query = urlParams.toString()
    const newURL = `${$page.url.pathname}${query ? `?${query}` : ""}`
    goto(newURL, { replaceState: true, noScroll: true, keepFocus: true })
  }

  // Sync state to the URL whenever any of it changes. The dependencies are
  // passed as arguments (like the other reactive statements in this file)
  // rather than tested in a condition — every change has to write, including
  // the ones that clear a value, so there is nothing to branch on. updateURL()
  // reads the current values itself and no-ops while initializing.
  $: sync_url(
    isInitializing,
    lens_selected,
    selected_id,
    starred_only,
    unlinked_expanded,
    pins,
    hidden_scores,
    hidden_usage,
    metric_axis_keys,
  )
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function sync_url(..._dependencies: unknown[]) {
    updateURL()
  }

  onMount(async () => {
    // Wait for page params to load
    await tick()

    initializeFromURL()

    await Promise.all([
      load_model_info(),
      load_available_models(),
      load_available_tools(project_id),
      load_task_prompts(project_id, task_id),
      get_run_configs(),
      get_evals(),
      get_summary(),
    ])

    validateStateFromURL()
    isInitializing = false
  })

  async function get_run_configs() {
    loading_run_configs = true
    try {
      await load_task_run_configs(project_id, task_id)
    } catch (err) {
      load_error = createKilnError(err)
    } finally {
      loading_run_configs = false
    }
  }

  async function get_evals() {
    loading_evals = true
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      evals = data
    } catch (err) {
      load_error = createKilnError(err)
    } finally {
      loading_evals = false
    }
  }

  async function get_summary() {
    loading_summary = true
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval_results_summary",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      summary = data
    } catch (err) {
      load_error = createKilnError(err)
    } finally {
      loading_summary = false
    }
  }

  async function fetch_eval_scores(run_config_id: string) {
    if (
      eval_scores_cache[run_config_id] ||
      eval_scores_loading[run_config_id] ||
      eval_scores_errors[run_config_id]
    ) {
      return // Already cached, loading, or errored
    }
    try {
      eval_scores_loading[run_config_id] = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_scores",
        {
          params: {
            path: { project_id, task_id, run_config_id },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      eval_scores_cache[run_config_id] = data
      delete eval_scores_errors[run_config_id]
    } catch (err) {
      const kilnError = createKilnError(err)
      eval_scores_errors[run_config_id] =
        kilnError.getMessage() || "Failed to fetch eval scores"
    } finally {
      eval_scores_loading[run_config_id] = false
    }
  }

  // Derived graph data
  $: run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || null
  $: prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null
  $: forest = build_forest(run_configs || [])
  $: layout = layout_forest(forest)
  $: lens_data = build_lens_data(summary, evals)

  $: selected_node = selected_id ? forest.nodes.get(selected_id) ?? null : null

  // Docking the detail panel takes 400px off the canvas (and undocking gives it
  // back), so the graph is re-fit to the new width - otherwise the transform
  // from the old width leaves it off-center or half out of view. Only the
  // transitions matter: re-fitting on every selection change would throw away
  // the pan/zoom the user set while clicking around the graph.
  let panel_was_docked = false
  $: refit_on_dock_change(!!selected_node)
  async function refit_on_dock_change(docked: boolean) {
    if (docked === panel_was_docked) {
      return
    }
    panel_was_docked = docked
    // Wait for the column to be added/removed before measuring the viewport.
    await tick()
    canvas?.fit()
  }

  // Lazily fetch the selected node's detailed eval scores
  $: if (selected_node && !selected_node.ghost) {
    fetch_eval_scores(selected_node.id)
  }

  $: unlinked_nodes = forest.unlinkedIds
    .map((id) => forest.nodes.get(id))
    .filter((n): n is EvoNode => !!n)

  // Compare set: explicit pins, or (when empty) the selected node plus its
  // primary parent chain, capped at 3 nodes.
  $: effective_pin_ids = compute_effective_pins(pins, selected_id, forest)
  function compute_effective_pins(
    explicit_pins: string[],
    current_id: string | null,
    current_forest: EvoForest,
  ): string[] {
    if (explicit_pins.length > 0) {
      return explicit_pins
    }
    if (!current_id) {
      return []
    }
    const chain: string[] = []
    let current = current_forest.nodes.get(current_id) ?? null
    while (current && !current.ghost && chain.length < 3) {
      chain.push(current.id)
      const parent_id = primary_parent_id(current)
      current = parent_id ? current_forest.nodes.get(parent_id) ?? null : null
    }
    return chain
  }

  $: pinned_nodes = effective_pin_ids
    .map((id) => forest.nodes.get(id))
    .filter((n): n is EvoNode => !!n && !n.ghost)

  // The matrix's usage rows and the inspector need per-config eval scores
  $: pinned_nodes.forEach((node) => fetch_eval_scores(node.id))
  $: pinned_ids = pinned_nodes.map((node) => node.id)

  // ---- Hidden rows --------------------------------------------------------
  // One filtered view of the score keys drives both the matrix rows and the
  // radar axes, so the two stay consistent. `lens_data.keyMetas` itself is left
  // whole: the strips, the aggregate lens and the lens dropdown are unaffected.
  $: hidden_score_set = new Set(hidden_scores)
  $: visible_key_metas = lens_data.keyMetas.filter(
    (meta) => !hidden_score_set.has(score_key_id(meta.evalId, meta.scoreKey)),
  )

  function hide_score_row(key: string) {
    if (!hidden_scores.includes(key)) {
      hidden_scores = [...hidden_scores, key]
    }
  }

  function show_score_row(key: string) {
    hidden_scores = hidden_scores.filter((hidden) => hidden !== key)
  }

  function hide_usage_row(key: string) {
    if (!hidden_usage.includes(key)) {
      hidden_usage = [...hidden_usage, key]
    }
  }

  function show_usage_row(key: string) {
    hidden_usage = hidden_usage.filter((hidden) => hidden !== key)
  }

  function show_all_hidden_rows() {
    hidden_scores = []
    hidden_usage = []
  }

  $: hidden_score_info = hidden_scores.map((key) => {
    const meta = lens_data.keyMetas.find(
      (candidate) => score_key_id(candidate.evalId, candidate.scoreKey) === key,
    )
    return {
      key,
      label: meta
        ? `${score_key_label(meta.scoreKey)} · ${meta.evalName}`
        : score_key_label(key.split("::")[1] ?? key),
    }
  })

  $: hidden_usage_info = hidden_usage.map((key) => ({
    key,
    label: USAGE_ROWS.find((row) => row.key === key)?.label ?? key,
  }))

  $: hidden_count = hidden_score_info.length + hidden_usage_info.length

  $: hidden_menu_items = [
    ...(hidden_score_info.length > 0
      ? [
          { label: "Show Score", header: true },
          ...hidden_score_info.map(
            (info): FloatingMenuItem => ({
              label: info.label,
              onclick: () => show_score_row(info.key),
            }),
          ),
        ]
      : []),
    ...(hidden_usage_info.length > 0
      ? [
          { label: "Show Metric", header: true },
          ...hidden_usage_info.map(
            (info): FloatingMenuItem => ({
              label: info.label,
              onclick: () => show_usage_row(info.key),
            }),
          ),
        ]
      : []),
    ...(hidden_count > 1
      ? [{ label: "Restore all", onclick: show_all_hidden_rows }]
      : []),
  ] as FloatingMenuItem[]

  // ---- Radar chart inputs -------------------------------------------------
  // The radar takes the same shape the old compare page feeds it; here it is
  // derived from the lens data instead of that page's comparison table.
  //
  // Criterion evals only. The two radars partition the score space by which
  // eval a key came from - quality here, metrics on the chart beside it - and
  // NOT by direction, which is what used to leave a higher-is-better metric
  // like cache_hit_rate on the quality ring between the pass/fail judges. See
  // criterion_key_metas.
  $: criterion_metas = criterion_key_metas(visible_key_metas)

  $: comparison_features = build_features(criterion_metas)
  function build_features(keyMetas: ScoreKeyMeta[]): ComparisonFeature[] {
    const by_eval = new Map<string, ScoreKeyMeta[]>()
    for (const meta of keyMetas) {
      const list = by_eval.get(meta.evalId) ?? []
      list.push(meta)
      by_eval.set(meta.evalId, list)
    }
    return [...by_eval.values()].map((metas) => ({
      category: metas[0].evalName,
      items: metas.map((meta) => ({
        label: score_key_label(meta.scoreKey),
        key: score_key_id(meta.evalId, meta.scoreKey),
      })),
      has_default_eval_config: true,
      eval_id: metas[0].evalId,
    }))
  }

  // Rebuilt when lens_data changes so the radar's reactive blocks notice
  $: get_model_value_raw = make_value_getter(lens_data)
  function make_value_getter(data: LensData) {
    return (modelKey: string | null, dataKey: string): number | null => {
      if (!modelKey) {
        return null
      }
      return data.raw.get(modelKey)?.get(dataKey) ?? null
    }
  }

  $: score_axis_maxes = (() => {
    const maxes: Record<string, number> = {}
    for (const meta of visible_key_metas) {
      const max = score_type_max(meta.type)
      if (max !== null) {
        maxes[score_key_id(meta.evalId, meta.scoreKey)] = max
      }
    }
    return maxes
  })()

  $: score_directions = (() => {
    const directions: Record<string, string> = {}
    for (const meta of visible_key_metas) {
      directions[score_key_id(meta.evalId, meta.scoreKey)] = meta.direction
    }
    return directions
  })()

  // Of the criterion scores, the radar still drops the lower-is-better and
  // informational ones (it reads "further from center is better"), so count
  // what's left to know whether it will draw anything at all.
  $: radar_axis_count = criterion_metas.filter(
    (meta) =>
      meta.direction !== "lower_is_better" &&
      meta.direction !== "informational",
  ).length
  $: radar_available =
    pinned_nodes.length > 0 && radar_axis_count >= MIN_RADAR_AXES

  // ---- Performance-metrics radar ------------------------------------------
  // The exact complement of the chart above: every key from a metrics eval,
  // whichever way it points, alongside the native usage rollup - so cost and
  // speed are read on their own terms instead of being mixed in with quality.
  // See $lib/utils/evolution/metric_axes.

  // Which axes actually have numbers, so a quantity reported by both the usage
  // rollup and an eval score key resolves to whichever source can be plotted.
  // Depends on the pinned set and the lazily fetched usage, so it is rebuilt
  // whenever either changes.
  $: metric_axis_has_value = make_metric_axis_has_value(
    get_metric_value,
    pinned_ids,
  )
  function make_metric_axis_has_value(
    getter: (run_config_id: string, key: string) => number | null,
    run_config_ids: string[],
  ) {
    return (key: string): boolean =>
      run_config_ids.some((id) => getter(id, key) !== null)
  }

  $: all_metric_axes = build_metric_axes(
    lens_data.keyMetas,
    metric_axis_has_value,
  )
  $: default_metric_keys = default_metric_axis_keys(all_metric_axes)
  $: shown_metric_keys = metric_axis_keys ?? default_metric_keys
  // Filtered from the canonical list rather than mapped from the selection, so
  // the axis order is stable no matter what order they were switched on in.
  $: shown_metric_axes = all_metric_axes.filter((axis) =>
    shown_metric_keys.includes(axis.key),
  )

  function toggle_metric_axis(key: string) {
    const selected = new Set(shown_metric_keys)
    if (selected.has(key)) {
      selected.delete(key)
    } else {
      selected.add(key)
    }
    metric_axis_keys = all_metric_axes
      .filter((axis) => selected.has(axis.key))
      .map((axis) => axis.key)
  }

  function reset_metric_axes() {
    metric_axis_keys = null
  }

  // Grouped under the same family headings the chart lays the axes out by, so
  // the menu reads in the same order as the ring.
  $: metric_menu_items = (() => {
    const items: FloatingMenuItem[] = []
    let family: MetricFamily | null = null
    for (const axis of all_metric_axes) {
      if (axis.family !== family) {
        family = axis.family
        items.push({ label: METRIC_FAMILY_LABELS[family], header: true })
      }
      const shown = shown_metric_keys.includes(axis.key)
      items.push({
        label: `${shown ? "✓" : "+"}  ${axis.label}`,
        // The axis is named for the virtue, so the menu names the quantity
        description: `${axis.valueLabel} · ${axis.evalName ?? "Usage rollup"}`,
        onclick: () => toggle_metric_axis(axis.key),
      })
    }
    if (metric_axis_keys !== null) {
      items.push({ label: "Reset to default", onclick: reset_metric_axes })
    }
    return items
  })()

  // What is left off, stated rather than silent. Informational score keys are
  // plotted here whenever the chart knows which end of their scale is the good
  // one - being a metric is the point of this chart - but one it cannot point
  // has no better end at all, and a radar can only say "further is better".
  $: metrics_not_shown_note = (() => {
    const parts: string[] = []
    const off = all_metric_axes.length - shown_metric_axes.length
    if (off > 0) {
      parts.push(`${off} ${off === 1 ? "metric" : "metrics"} not selected`)
    }
    const directionless = directionless_key_count(lens_data.keyMetas)
    if (directionless > 0) {
      parts.push(
        `${directionless} ${
          directionless === 1 ? "score" : "scores"
        } with no better direction`,
      )
    }
    return parts.length > 0 ? parts.join(", ") : null
  })()

  // Score keys come from the lens; the usage rollup comes from the lazily
  // fetched per-config summary. Both caches are passed in as arguments so the
  // getter is rebuilt (and the chart redrawn) when either arrives.
  $: get_metric_value = make_metric_value_getter(lens_data, eval_scores_cache)
  function make_metric_value_getter(
    data: LensData,
    cache: Record<string, RunConfigEvalScoresSummary>,
  ) {
    return (run_config_id: string, key: string): number | null => {
      if (!key.startsWith(USAGE_KEY_PREFIX)) {
        return data.raw.get(run_config_id)?.get(key) ?? null
      }
      const usage = cache[run_config_id]?.mean_usage
      if (!usage) {
        return null
      }
      switch (key) {
        case COST_KEY:
          return usage.mean_cost ?? null
        case TOTAL_TOKENS_KEY:
          return usage.mean_total_tokens ?? null
        case LATENCY_KEY:
          return usage.mean_total_llm_latency_ms ?? null
        case INPUT_TOKENS_KEY:
          return usage.mean_input_tokens ?? null
        case OUTPUT_TOKENS_KEY:
          return usage.mean_output_tokens ?? null
        default:
          return null
      }
    }
  }

  function toggle_pin(id: string) {
    if (pins.includes(id)) {
      pins = pins.filter((pin) => pin !== id)
    } else if (pins.length === 0) {
      // First explicit pin materializes the default compare set
      const seeded = effective_pin_ids.filter((pin) => pin !== id)
      pins = [...seeded, id].slice(0, MAX_PINS)
    } else if (pins.length < MAX_PINS) {
      pins = [...pins, id]
    }
  }

  // Judge/eval config behind an (eval, run config) cell: prefer the config
  // that actually produced the cached scores, fall back to the eval's default.
  function resolve_eval_config_id(
    eval_id: string,
    run_config_id: string,
  ): string | null {
    const from_scores = eval_scores_cache[run_config_id]?.eval_results.find(
      (result) => result.eval_id === eval_id,
    )?.eval_config_result?.eval_config_id
    if (from_scores) {
      return from_scores
    }
    return summary?.evals_by_id[eval_id]?.default_judge_config_id ?? null
  }

  function open_inspector(eval_id: string, run_config_id: string) {
    const eval_config_id = resolve_eval_config_id(eval_id, run_config_id)
    if (!eval_config_id) {
      return
    }
    inspector = {
      eval_id,
      eval_config_id,
      run_config_id,
      eval_name:
        evals.find((evaluator) => evaluator.id === eval_id)?.name ??
        summary?.evals_by_id[eval_id]?.name ??
        "Eval",
      run_config_name: forest.nodes.get(run_config_id)?.name ?? null,
    }
  }

  // Lens dropdown options
  $: lens_options = build_lens_options(lens_data.keyMetas)
  function build_lens_options(keyMetas: ScoreKeyMeta[]): OptionGroup[] {
    const groups: OptionGroup[] = [
      {
        options: [
          {
            label: "Aggregate score",
            value: "aggregate",
            description: "Mean of all normalized eval scores",
          },
        ],
      },
    ]
    const by_eval = new Map<string, ScoreKeyMeta[]>()
    for (const meta of keyMetas) {
      const list = by_eval.get(meta.evalId) ?? []
      list.push(meta)
      by_eval.set(meta.evalId, list)
    }
    for (const metas of by_eval.values()) {
      groups.push({
        label: metas[0].evalName,
        options: metas.map((meta) => ({
          label: score_key_label(meta.scoreKey),
          value: score_key_id(meta.evalId, meta.scoreKey),
        })),
      })
    }
    return groups
  }

  // Per-node display data, shared by the canvas and the unlinked grid
  $: displays = build_displays(
    forest.nodes,
    lens_data,
    lens,
    starred_only,
    $model_info,
    prompts,
  )
  function build_displays(
    nodes: Map<string, EvoNode>,
    data: LensData,
    current_lens: Lens,
    starred_filter: boolean,
    provider_models: ProviderModels | null,
    task_prompts: PromptResponse | null,
  ): Record<string, NodeDisplay> {
    // "Best" = highest normalized value under the current lens
    let best_id: string | null = null
    let best_value = -1
    for (const node of nodes.values()) {
      if (node.ghost) {
        continue
      }
      const value = normalized_lens_value(data, node.id, current_lens)
      if (value !== null && value > best_value) {
        best_value = value
        best_id = node.id
      }
    }

    const result: Record<string, NodeDisplay> = {}
    for (const node of nodes.values()) {
      const normalized = node.ghost
        ? null
        : normalized_lens_value(data, node.id, current_lens)
      const raw = node.ghost
        ? null
        : raw_lens_value(data, node.id, current_lens)
      const cells = node.ghost
        ? []
        : strip_cells(data, node.id, primary_parent_id(node))
      result[node.id] = {
        lens_color: lens_color(normalized),
        lens_value: raw === null ? null : raw.toFixed(2),
        strip: cells,
        subtitle: node_subtitle(node, provider_models, task_prompts),
        best: node.id === best_id,
        dimmed: starred_filter && !node.starred && !node.ghost,
      }
    }
    return result
  }

  function node_subtitle(
    node: EvoNode,
    provider_models: ProviderModels | null,
    task_prompts: PromptResponse | null,
  ): string {
    const props = node.config?.run_config_properties
    if (!props) {
      return ""
    }
    if (isMcpRunConfig(props)) {
      return props.tool_reference?.tool_name ?? "MCP Tool"
    }
    if (isKilnAgentRunConfig(props)) {
      return `${model_name(props.model_name, provider_models)} · ${prompt_name_from_id(props.prompt_id, task_prompts)}`
    }
    return ""
  }

  function handle_select(id: string | null) {
    selected_id = id
  }
</script>

<AppPage
  title="Compare V2"
  subtitle="Run config lineage, scores, and drill-downs"
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if load_error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Evolution Data</div>
      <div class="text-error text-sm">
        {load_error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else}
    <!-- Toolbar -->
    <div class="flex flex-row items-center gap-4 mb-4 flex-wrap">
      <div class="w-72">
        <FancySelect
          aria_label="Score lens"
          options={lens_options}
          bind:selected={lens_selected}
        />
      </div>
      <label class="flex items-center gap-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          class="toggle toggle-sm"
          bind:checked={starred_only}
        />
        Starred only
      </label>
      <div class="flex-grow"></div>
      {#if forest.edges.length > 0}
        <div class="join">
          <button
            class="btn btn-sm btn-outline join-item"
            title="Zoom out"
            on:click={() => canvas?.zoom_by(1 / 1.25)}
          >
            −
          </button>
          <button
            class="btn btn-sm btn-outline join-item"
            title="Fit graph to view"
            on:click={() => canvas?.fit()}
          >
            Fit
          </button>
          <button
            class="btn btn-sm btn-outline join-item"
            title="Zoom in"
            on:click={() => canvas?.zoom_by(1.25)}
          >
            +
          </button>
        </div>
      {/if}
    </div>

    <!-- The three sections stack full width: graph, radar, matrix. Each one
         wants the whole page - a two-column row forced both the DAG and the
         radar into aspect ratios that suited neither. -->

    <!-- Section 1: the lineage graph, with its own pan/zoom inside. When a node
         is selected its detail panel docks as a right-hand column of this same
         card - an IDE-style side panel, not an overlay: nothing floats, nothing
         overlaps the radar below, and the canvas simply takes the width that's
         left. -->
    <div
      class="min-w-0 h-[560px] min-h-[560px] flex flex-row rounded-lg border border-gray-200 overflow-hidden"
    >
      <div class="flex-1 min-w-0">
        {#if forest.edges.length > 0}
          <EvolutionCanvas
            bind:this={canvas}
            {forest}
            {layout}
            {displays}
            {selected_id}
            {project_id}
            {prompts}
            {pins}
            on:select={(event) => handle_select(event.detail)}
            on:toggle_pin={(event) => toggle_pin(event.detail)}
          />
        {:else}
          <!-- Empty state: no lineage recorded at all. Fills the same card, so
               the page doesn't jump when lineage first appears. -->
          <div
            class="h-full bg-gray-50 px-6 flex flex-col justify-center items-center text-center"
          >
            <div class="text-lg font-medium text-gray-900 mb-1">
              No lineage recorded yet
            </div>
            <div class="text-sm text-gray-500 max-w-lg">
              None of this task's run configs declare a parent. When a run
              config is derived from another, the link appears here as a lineage
              graph.
            </div>
          </div>
        {/if}
      </div>

      {#if selected_node}
        <!-- Intro-only transition: the column takes its full width immediately
             (so the canvas re-fits against a settled layout) and the panel
             fades in over it. An outro would hold the width open while the
             canvas has already been told to re-fit. -->
        <div
          class="w-[400px] flex-none border-l border-gray-200 bg-white overflow-hidden"
          in:fly={{ x: 16, duration: 150, easing: cubicOut }}
        >
          <NodeDetailPanel
            node={selected_node}
            {forest}
            {project_id}
            {task_id}
            {lens_data}
            eval_scores={eval_scores_cache[selected_node.id] ?? null}
            eval_scores_loading={eval_scores_loading[selected_node.id] ?? false}
            eval_scores_error={eval_scores_errors[selected_node.id] ?? null}
            pinned={pins.includes(selected_node.id)}
            on:close={() => handle_select(null)}
            on:select={(event) => handle_select(event.detail)}
            on:toggle_pin={(event) => toggle_pin(event.detail)}
            on:open_pane={(event) => (pane_target = event.detail)}
            on:inspect={(event) =>
              selected_node &&
              open_inspector(event.detail.eval_id, selected_node.id)}
          />
        </div>
      {/if}
    </div>

    <!-- Section 2: the two radars, side by side - quality on the left, what it
         cost to get it on the right. They only pair up once there is room for
         two rings plus their axis names (each needs roughly 540px before the
         plot starts losing to the labels), so below xl they stack and each one
         is page-width again.

         Height is the only thing a radar can grow into, so the floor is
         generous: the chart's own 640px box plus its card header and padding.
         Tall enough for wrapped axis names all the way round the outer ring
         plus the scrolling legend underneath.

         The two cards are the same height, which is what makes the row read as
         a pair rather than two things that happen to be adjacent. Grid rows
         size to their tallest item and both columns stretch to it, so each card
         is `h-full` inside a column that carries the floor - and neither card
         may add a margin of its own, which would come straight out of that
         height on one side only. -->
    <div class="mt-6 grid grid-cols-1 xl:grid-cols-2 gap-6 items-stretch">
      <div class="min-w-0 min-h-[800px] flex flex-col">
        {#if radar_available}
          <CompareRadarChart
            comparisonFeatures={comparison_features}
            getModelValueRaw={get_model_value_raw}
            run_configs={run_configs ?? []}
            model_info={$model_info}
            {prompts}
            selectedRunConfigIds={pinned_ids}
            scoreAxisMaxes={score_axis_maxes}
            scoreDirections={score_directions}
            legend_position="bottom"
          />
        {:else}
          <div
            class="flex-1 bg-white border border-gray-200 rounded-lg p-6 flex flex-col justify-center items-center text-center"
          >
            <div class="text-lg font-medium text-gray-900 mb-1">
              {pinned_nodes.length === 0
                ? "Pin configs to compare"
                : "Not enough scores to plot"}
            </div>
            <div class="text-sm text-gray-500 max-w-md">
              {#if pinned_nodes.length === 0}
                Select a run config, or hover a card and hit Pin, to build a
                compare set. Up to {MAX_PINS} configs are charted here and listed
                in the table below.
              {:else}
                A radar chart needs at least {MIN_RADAR_AXES} higher-is-better scores.
                Every score is still in the comparison table below.
              {/if}
            </div>
          </div>
        {/if}
      </div>

      <div class="min-w-0 min-h-[800px] flex flex-col">
        <CompareMetricsRadarChart
          axes={shown_metric_axes}
          getMetricValue={get_metric_value}
          run_configs={run_configs ?? []}
          model_info={$model_info}
          {prompts}
          selectedRunConfigIds={pinned_ids}
          notShownNote={metrics_not_shown_note}
        >
          <FloatingMenu slot="controls" items={metric_menu_items} width="w-64">
            <button
              slot="trigger"
              type="button"
              class="btn btn-sm font-normal"
              title="Choose which metrics are plotted"
            >
              Axes ({shown_metric_axes.length})
            </button>
          </FloatingMenu>
        </CompareMetricsRadarChart>
      </div>
    </div>

    <!-- Section 3: the comparison matrix, full page width -->
    {#if pinned_nodes.length > 0}
      <div class="mt-6">
        <div class="flex items-center gap-2 mb-2">
          <div class="text-sm font-medium text-gray-900">
            Comparison ({pinned_nodes.length}
            {pinned_nodes.length === 1 ? "config" : "configs"})
          </div>
          {#if hidden_count > 0}
            <FloatingMenu items={hidden_menu_items} width="w-72">
              <button
                slot="trigger"
                type="button"
                class="btn btn-xs btn-outline rounded-full font-normal"
                title="Rows hidden from the table and the chart"
              >
                Hidden ({hidden_count})
              </button>
            </FloatingMenu>
          {/if}
        </div>
        <CompareMatrix
          {pinned_nodes}
          {lens_data}
          {eval_scores_cache}
          {eval_scores_loading}
          hidden_score_keys={hidden_scores}
          hidden_usage_keys={hidden_usage}
          on:select={(event) => handle_select(event.detail)}
          on:inspect={(event) =>
            open_inspector(event.detail.eval_id, event.detail.run_config_id)}
          on:hide_score={(event) => hide_score_row(event.detail)}
          on:hide_usage={(event) => hide_usage_row(event.detail)}
        />
      </div>
    {/if}

    <UnlinkedSection
      nodes={unlinked_nodes}
      {displays}
      {selected_id}
      {pins}
      expanded={forest.edges.length === 0 || unlinked_expanded}
      collapsible={forest.edges.length > 0}
      on:toggle={() => (unlinked_expanded = !unlinked_expanded)}
      on:select={(event) => handle_select(event.detail)}
      on:toggle_pin={(event) => toggle_pin(event.detail)}
    />
  {/if}
</AppPage>

<!-- Artifact previews (prompt text, run config properties) are modals: docking
     a second column beside the detail panel would leave the canvas nothing to
     draw in, and this content reads better wide than tall. Same treatment the
     eval inspector already gets. -->
{#if !loading && !load_error && pane_target}
  <ArtifactPane
    target={pane_target}
    {project_id}
    {task_id}
    {prompts}
    on:close={() => (pane_target = null)}
  />
{/if}

{#if inspector}
  {#key `${inspector.eval_id}::${inspector.eval_config_id}::${inspector.run_config_id}`}
    <EvalInspector
      {project_id}
      {task_id}
      eval_id={inspector.eval_id}
      eval_config_id={inspector.eval_config_id}
      run_config_id={inspector.run_config_id}
      eval_name={inspector.eval_name}
      run_config_name={inspector.run_config_name}
      on:close={() => (inspector = null)}
    />
  {/key}
{/if}
