<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { components } from "$lib/api_schema"
  import type { Eval, TaskRunConfig } from "$lib/types"
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
    run_count,
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
  import CompareMetricsBarChart from "$lib/components/compare_metrics_bar_chart.svelte"
  import CompareParallelChart from "$lib/components/compare_parallel_chart.svelte"
  import ComparePriceLatencyChart from "$lib/components/compare_price_latency_chart.svelte"
  import type { ParallelAxisSpec } from "$lib/utils/evolution/parallel_bands"
  import {
    build_metric_axes,
    criterion_key_metas,
    default_metric_axis_keys,
    directionless_key_count,
    format_metric_value,
    known_metric_axis_keys,
    METRIC_FAMILIES,
    METRIC_FAMILY_LABELS,
    COST_KEY,
    INPUT_TOKENS_KEY,
    LATENCY_KEY,
    OUTPUT_TOKENS_KEY,
    TOTAL_TOKENS_KEY,
    USAGE_KEY_PREFIX,
    metric_eval_ids,
    metric_row_info,
    score_row_label,
    toggled_metric_axis_keys,
    usage_row_family,
    visible_metric_axes,
    type MetricAxis,
    type MetricFamily,
  } from "$lib/utils/evolution/metric_axes"
  import { capped_rank_scores } from "$lib/utils/evolution/rank_score"
  import {
    build_score_families,
    family_for_eval,
    family_rank,
    order_families,
    type ScoreFamily,
  } from "$lib/utils/evolution/score_families"
  import {
    weakest_family_quality,
    type QualityBreakdown,
  } from "$lib/utils/evolution/quality_score"
  import {
    build_price_latency_points,
    quality_gate_cuts,
    split_by_gate,
  } from "$lib/utils/evolution/price_latency"
  import { spec_descriptions_by_eval } from "$lib/utils/evolution/axis_help"
  import {
    series_color_map,
    series_display_map,
  } from "$lib/utils/evolution/series_identity"
  import {
    hidden_run_config_ids,
    reconcile_visibility,
    visible_ids,
  } from "$lib/utils/evolution/visibility_store"
  import {
    DEFAULT_MATCH_PREDICATE,
    MATCH_LABELS,
    MATCH_PREDICATES,
    MIN_MATCHED_N,
    build_matched_lens_data,
    build_matched_usage,
    match_param,
    matched_items_by_eval,
    parse_match_param,
    recovery_hints,
    tool_call_source,
    type MatchPredicate,
    type MatchedUsage,
    type RunIndexes,
  } from "$lib/utils/evolution/run_matching"
  import ComparisonBasis, {
    type BasisError,
    type BasisEval,
    type BasisRecovery,
  } from "./comparison_basis.svelte"
  import EvolutionLegend from "./evolution_legend.svelte"
  import EvolutionCanvas from "./evolution_canvas.svelte"
  import NodeDetailPanel from "./node_detail_panel.svelte"
  import UnlinkedSection from "./unlinked_section.svelte"
  import CompareMatrix, {
    USAGE_ROWS,
    type MatrixGroup,
    type MatrixRow,
    type UsageRowKey,
  } from "./compare_matrix.svelte"
  import EvalInspector from "./eval_inspector.svelte"
  import FloatingMenu from "$lib/ui/floating_menu.svelte"
  import type { FloatingMenuItem } from "$lib/ui/floating_menu_types"
  import ArtifactPane, { type ArtifactPaneTarget } from "./artifact_pane.svelte"

  type EvalResultsSummaryResponse =
    components["schemas"]["EvalResultsSummaryResponse"]
  type Spec = components["schemas"]["Spec"]
  type RunConfigEvalScoresSummary =
    components["schemas"]["RunConfigEvalScoresSummary"]
  type EvalRunIndexResponse = components["schemas"]["EvalRunIndexResponse"]

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
  // Specs, for the quality radar's families. They carry the only grouping of
  // the criteria that exists anywhere - see score_families - and nothing else
  // on the page needs them, so a failure to load is not a page error: the
  // charts simply render ungrouped.
  let specs: Spec[] = []

  // Lazy per-run-config eval scores (n_used + usage footer in detail panel).
  // Keyed by run config id alone: the split scopes the whole page, so a change
  // of split empties all three rather than growing a second dimension of keys
  // that every consumer would have to know about.
  let eval_scores_cache: Record<string, RunConfigEvalScoresSummary> = {}
  let eval_scores_loading: Record<string, boolean> = {}
  let eval_scores_errors: Record<string, string> = {}

  // Per-run rows for the configs being compared, fetched only while a matching
  // predicate is active. Keyed and emptied exactly like eval_scores_cache
  // above, for the same reason: the split scopes the whole page.
  let eval_run_index_cache: RunIndexes = {}
  let eval_run_index_loading: Record<string, boolean> = {}
  let eval_run_index_errors: Record<string, string> = {}

  // Which dataset split the page is reading.
  //
  // A run config is iterated against TRAIN and only measured on TEST at the
  // end, so until this existed the page compared configs on the one slice most
  // of them had never been run against: every config whose work was done on
  // train read as "no score", indistinguishable from one nobody ever ran. The
  // scores, the metrics and the tables are all scoped by it together - a page
  // showing test quality beside train cost would be a lie of composition.
  //
  // "test" is the default because it is what the page has always shown, and it
  // is sent as an omitted parameter rather than split=test: the two mean the
  // same thing to the API (each eval's own set), and omitting keeps the URL
  // and the request identical to what every other caller sends.
  const SPLIT_VIEWS = ["test", "train", "val", "all"] as const
  type SplitView = (typeof SPLIT_VIEWS)[number]
  const SPLIT_LABELS: Record<SplitView, string> = {
    test: "Test",
    train: "Train",
    val: "Val",
    all: "All runs",
  }
  let split_view: SplitView = "test"
  // The split the loaded summary belongs to, so a change of split is a reload
  // and the reload is not mistaken for a first load
  let loaded_split: SplitView | null = null
  // A split change refetches, but not behind the full-page spinner: the graph
  // is the reader's place in the page and it should not vanish under them for
  // a toggle.
  let summary_refreshing = false

  // UI state (round-tripped through the URL)
  // "none" by default: see the Lens type. The card's own facts - runs and the
  // delta strip - carry it, and a lens is chosen when a question needs one.
  let lens_selected: unknown = "none"
  let selected_id: string | null = null
  let starred_only = false
  let unlinked_expanded = false
  let pins: string[] = []
  // Matrix rows the user hid: score rows keyed `${evalId}::${scoreKey}`, usage
  // rows keyed by their metric. Hiding is a view concern, and it means one
  // thing in both tracks - a hidden row leaves its table AND its axis leaves
  // the radar beside it. Neither touches the lens aggregate or the node delta
  // strips, which stay full-coverage.
  let hidden_scores: string[] = []
  let hidden_usage: string[] = []
  // Axes on the performance-metrics radar. Null means "follow the default set",
  // which is what almost every visit wants and what keeps the URL clean; a list
  // means the user picked. Kept separate from hidden_scores/hidden_usage on
  // purpose, because the two controls compose rather than overlap: hiding says
  // what is in the comparison at all, this says which of what is left is worth
  // an axis. So an axis being off the chart never takes its number out of the
  // table, and a hidden row never edits this selection - it comes back with its
  // axis on if that is how it went away.
  let metric_axis_keys: string[] | null = null
  // Performance metrics the reader ADDED to the quality parallel chart, as
  // extra rank axes. Empty by default, and empty is the whole design: that
  // chart's subject is the quality scores and their intervals, and a metric
  // only belongs on it when the reader has a question that crosses the two
  // ("the config that wins on P1 - what did it cost?"). Nobody's default view
  // should be a mixed chart they did not ask for.
  //
  // A list rather than metric_axis_keys' null-means-default, because there is
  // no default set to fall back to: [] IS the intent, so it needs no sentinel
  // and the URL stays clean without one.
  let parallel_metric_keys: string[] = []
  // The quality floor on the price/latency chart, as a 0..1 aggregate score.
  // Null - no gate - is the default: the gate is a claim about what "good
  // enough" means on this task, and the page has no business asserting one. In
  // the URL because it is a DECISION rather than a view setting: the chart is
  // read by someone arguing for a config, and the link they send has to carry
  // the floor they argued under.
  let quality_floor: number | null = null

  // Which conversations the comparison is made over. See run_matching: at "all"
  // every config is measured on whatever runs it happens to have, which is what
  // this page used to do and what makes two configs on one axis not necessarily
  // a comparison at all.
  //
  // The default is `shared` (DEFAULT_MATCH_PREDICATE), so the page opens on the
  // basis where a difference between two means is a difference between the
  // CONFIGS. On a single pinned config every predicate is the identity and the
  // banner reports "All runs", so nothing about a one-config view changes.
  // "all" is the explicit opt-out and is what serializes into the URL now.
  //
  // It is in the URL for the same reason quality_floor is: a Compare V2 link is
  // an argument someone sends, and the basis it was argued under has to travel
  // with it.
  let match_predicate: MatchPredicate = DEFAULT_MATCH_PREDICATE

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
    const urlSplit = urlParams.get("split")
    if (urlSplit && (SPLIT_VIEWS as readonly string[]).includes(urlSplit)) {
      split_view = urlSplit as SplitView
    }
    // Validated against the enum inside parse_match_param, where an unknown
    // value is the default rather than an error - a hand-edited URL must not be
    // able to put the page in a basis it cannot name.
    match_predicate = parse_match_param(urlParams.get("match"))
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
    // Same discipline as `metrics` above, and the same reason to test against
    // null: `pmetrics=` present but empty is a legal, meaningful state (the
    // reader cleared the axes), and it happens to resolve to the same [] the
    // default is. Unknown keys are dropped in validateStateFromURL.
    const urlParallelMetrics = urlParams.get("pmetrics")
    if (urlParallelMetrics !== null) {
      parallel_metric_keys = [
        ...new Set(
          urlParallelMetrics
            .split(",")
            .map((key) => key.trim())
            .filter((key) => key.length > 0),
        ),
      ]
    }
    // A floor outside 0..1 is not a floor anyone could have set from the menu,
    // and clamping a hand-edited one would invent a gate the reader never
    // chose - so anything unparseable or out of range drops back to no gate.
    const urlQualityFloor = urlParams.get("quality_floor")
    if (urlQualityFloor !== null) {
      const parsed = parseFloat(urlQualityFloor)
      if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 1) {
        quality_floor = parsed
      }
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
    if (metric_axis_keys !== null || parallel_metric_keys.length > 0) {
      const known_metric_keys = known_metric_axis_keys(lens_data.keyMetas)
      if (metric_axis_keys !== null) {
        metric_axis_keys = metric_axis_keys.filter((key) =>
          known_metric_keys.has(key),
        )
      }
      // The parallel chart's added axes come from the same catalog, so they
      // are validated against the same set - a stale link must not leave the
      // chart holding a rank axis for a metric this task never reports.
      parallel_metric_keys = parallel_metric_keys.filter((key) =>
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
      lens_selected = "none"
    }
  }

  function updateURL() {
    if (isInitializing) {
      return
    }
    const urlParams = new URLSearchParams($page.url.search)

    const serialized_lens = lens_key(lens)
    if (serialized_lens !== "none") {
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
    if (split_view !== "test") {
      urlParams.set("split", split_view)
    } else {
      urlParams.delete("split")
    }
    // Same omitted-default discipline as the split, around the new default:
    // `shared` stays absent and `all` is written, because pooling every run is
    // now the position a link has to state.
    const serialized_match = match_param(match_predicate)
    if (serialized_match !== null) {
      urlParams.set("match", serialized_match)
    } else {
      urlParams.delete("match")
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
    // Empty is the default here, so it stays implicit - no `pmetrics=` in the
    // URL until the reader adds an axis, and clearing them takes it back out.
    if (parallel_metric_keys.length > 0) {
      urlParams.set("pmetrics", parallel_metric_keys.join(","))
    } else {
      urlParams.delete("pmetrics")
    }
    // Only once a gate has been set; "off" is the default and stays implicit
    if (quality_floor !== null) {
      urlParams.set("quality_floor", String(quality_floor))
    } else {
      urlParams.delete("quality_floor")
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
    split_view,
    match_predicate,
    starred_only,
    unlinked_expanded,
    pins,
    hidden_scores,
    hidden_usage,
    metric_axis_keys,
    parallel_metric_keys,
    quality_floor,
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
      get_specs(),
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

  // Best-effort: specs only supply the family grouping, so a task that has none
  // (or a request that fails) leaves the page fully functional and ungrouped.
  // Deliberately not counted in `loading` and never sets load_error.
  async function get_specs() {
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (fetch_error || !data) {
        return
      }
      specs = data
    } catch {
      specs = []
    }
  }

  // The split as the API takes it: omitted for "test", which is what an
  // unscoped request has always returned.
  function split_query(split: SplitView): { split?: SplitView } {
    return split === "test" ? {} : { split }
  }

  async function get_summary(refresh: boolean = false) {
    const requested_split = split_view
    loaded_split = requested_split
    if (refresh) {
      summary_refreshing = true
    } else {
      loading_summary = true
    }
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval_results_summary",
        {
          params: {
            path: { project_id, task_id },
            query: split_query(requested_split),
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      // A toggle while this was in flight makes the answer the wrong split's;
      // the newer request owns the state.
      if (requested_split !== split_view) {
        return
      }
      summary = data
    } catch (err) {
      if (requested_split === split_view) {
        load_error = createKilnError(err)
      }
    } finally {
      if (refresh) {
        summary_refreshing = false
      } else {
        loading_summary = false
      }
    }
  }

  // A split change reloads everything the split scopes: the task-wide summary
  // and every per-config score already fetched. The caches are emptied rather
  // than re-keyed, and the pinned/selected reactive statements below refill
  // them for whatever is on screen.
  $: reload_for_split(isInitializing, split_view)
  function reload_for_split(initializing: boolean, next: SplitView) {
    if (initializing || loaded_split === null || loaded_split === next) {
      return
    }
    eval_scores_cache = {}
    eval_scores_loading = {}
    eval_scores_errors = {}
    eval_run_index_cache = {}
    eval_run_index_loading = {}
    eval_run_index_errors = {}
    get_summary(true)
  }

  async function fetch_eval_scores(run_config_id: string) {
    if (
      eval_scores_cache[run_config_id] ||
      eval_scores_loading[run_config_id] ||
      eval_scores_errors[run_config_id]
    ) {
      return // Already cached, loading, or errored
    }
    const requested_split = split_view
    try {
      eval_scores_loading[run_config_id] = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_scores",
        {
          params: {
            path: { project_id, task_id, run_config_id },
            query: split_query(requested_split),
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      // The caches were emptied by the split that superseded this request -
      // writing into them now would file one split's numbers under another.
      if (requested_split !== split_view) {
        return
      }
      eval_scores_cache[run_config_id] = data
      delete eval_scores_errors[run_config_id]
    } catch (err) {
      if (requested_split !== split_view) {
        return
      }
      const kilnError = createKilnError(err)
      eval_scores_errors[run_config_id] =
        kilnError.getMessage() || "Failed to fetch eval scores"
    } finally {
      if (requested_split === split_view) {
        eval_scores_loading[run_config_id] = false
      }
    }
  }

  // The per-run rows a matching predicate needs, fetched lazily and never at
  // the default predicate: at "all" the page's network cost is exactly what it
  // was before this feature existed. Activation fetches the current basis;
  // pinning a config while a predicate is active fetches the newcomer.
  //
  // Same stale-split guard as fetch_eval_scores above, for the same reason: a
  // split toggle empties the caches, and a request in flight when that happened
  // would file one split's rows under another.
  async function fetch_eval_run_index(run_config_id: string) {
    if (
      eval_run_index_cache[run_config_id] ||
      eval_run_index_loading[run_config_id] ||
      eval_run_index_errors[run_config_id]
    ) {
      return // Already cached, loading, or errored
    }
    const requested_split = split_view
    try {
      eval_run_index_loading[run_config_id] = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_run_index",
        {
          params: {
            path: { project_id, task_id, run_config_id },
            query: split_query(requested_split),
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      if (requested_split !== split_view) {
        return
      }
      eval_run_index_cache[run_config_id] = data as EvalRunIndexResponse
      delete eval_run_index_errors[run_config_id]
    } catch (err) {
      if (requested_split !== split_view) {
        return
      }
      const kilnError = createKilnError(err)
      eval_run_index_errors[run_config_id] =
        kilnError.getMessage() || "Failed to fetch eval runs"
    } finally {
      if (requested_split === split_view) {
        eval_run_index_loading[run_config_id] = false
      }
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

  // How much of the task the current split actually covers. An eval with no
  // train filter contributes nothing to the train view, and a page that just
  // showed fewer bars would read as "these configs were never run" rather than
  // "this eval has no train set" - so the difference is stated rather than
  // drawn. Only for a split view: each eval owns its test set by definition.
  $: split_coverage = summarize_split_coverage(summary, split_view)
  function summarize_split_coverage(
    current: EvalResultsSummaryResponse | null,
    split: SplitView,
  ): { missing: number; total: number } | null {
    if (!current || split === "test" || split === "all") {
      return null
    }
    const infos = Object.values(current.evals_by_id)
    const missing = infos.filter(
      (info) => info.split_available === false,
    ).length
    if (missing === 0) {
      return null
    }
    return { missing, total: infos.length }
  }

  // What the charts say they are showing. Null for the default view, which is
  // the one the cards' own subtitles already describe.
  $: split_scope_label =
    split_view === "test" ? null : `${SPLIT_LABELS[split_view]} split`

  // The same thing for a card that has to name the split even when it is the
  // default one. The price/latency chart is the card someone screenshots to
  // argue for a config, and "$0.31 a conversation" is a different claim on
  // train than on test - so that card states the lane unconditionally, and
  // this is the label it states. "All runs" is already a phrase; the others
  // are named for the split they are.
  // ...and it has to state the matching basis for exactly the same reason: over
  // 23 matched conversations "$0.31 a conversation" is a different claim than
  // over every run a config ever had.
  $: stated_scope_label = `${
    split_view === "all"
      ? SPLIT_LABELS.all
      : `${SPLIT_LABELS[split_view]} split`
  }${
    matching_active
      ? ` · ${MATCH_LABELS[match_result.applied].toLowerCase()}${matched_conversation_phrase}`
      : ""
  }`

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

  // ---- The comparison basis ------------------------------------------------
  // Stage 2 of the composition: the split (stage 1, server-side) scopes each
  // eval's item universe, matching then filters items per eval over the PINNED
  // set, aggregation follows, and only then does the legend decide what is
  // drawn. Legend visibility deliberately does NOT feed this - hiding a chip is
  // documented on this page as decluttering an image, not as removing a config
  // from the comparison (both tables still show hidden configs), and a legend
  // toggle that silently moved every mean and every N would make that false.

  $: if (match_predicate !== "all") {
    pinned_ids.forEach((id) => fetch_eval_run_index(id))
  }

  // A config whose rows could not be read is left OUT of the basis rather than
  // treated as a config that ran nothing: the latter would empty every
  // intersection on the page and blame the data. Its own cells still gap (it
  // has no matched rows), and the banner names the failure.
  $: basis_ids = pinned_ids.filter((id) => !eval_run_index_errors[id])

  // Every basis config has to have answered - or failed - before a predicate
  // can be applied. Until then the page keeps showing what it was showing and
  // the banner says it is matching; the alternative is charts that empty and
  // refill, or worse, pooled numbers presented under a matched banner.
  $: basis_indexes_ready = basis_ids.every(
    (id) => !!eval_run_index_cache[id] || !!eval_run_index_errors[id],
  )
  $: matching_pending = match_predicate !== "all" && !basis_indexes_ready

  $: tool_source = tool_call_source(lens_data.keyMetas, eval_run_index_cache)
  // The metrics partition goes in because two of the matcher's decisions are
  // about the CRITERIA: whether a shape predicate has left them readable, and
  // what denominator the banner quotes. A metrics eval scores every
  // conversation on the task and would carry both votes on its own.
  $: is_metric_eval_id = (evalId: string): boolean =>
    metric_eval_id_set.has(evalId)
  $: match_result = matched_items_by_eval(
    eval_run_index_cache,
    basis_ids,
    matching_pending ? "all" : match_predicate,
    tool_source,
    is_metric_eval_id,
  )
  $: matching_active = match_result.applied !== "all"

  // The swap that carries the whole feature: every chart and both tables read
  // their numbers through page-level getters, so pointing those getters at
  // matched data filters the entire page without a single chart knowing.
  $: effective_lens_data = matching_active
    ? build_matched_lens_data(
        lens_data,
        eval_run_index_cache,
        basis_ids,
        match_result.items_by_eval,
      )
    : lens_data
  $: matched_usage = matching_active
    ? build_matched_usage(
        eval_run_index_cache,
        basis_ids,
        match_result.items_by_eval,
      )
    : null

  // What the banner states. Names rather than ids: an id is not a fact the
  // reader can act on.
  $: eval_names_by_id = new Map(
    lens_data.keyMetas.map((meta) => [meta.evalId, meta.evalName]),
  )
  $: config_label = (id: string): string =>
    series_labels[id] ?? forest.nodes.get(id)?.name ?? id
  $: basis_evals = match_result.evals.map(
    (entry): BasisEval => ({
      evalId: entry.evalId,
      name: eval_names_by_id.get(entry.evalId) ?? "Eval",
      matched: entry.matched,
      shared: entry.shared,
      universe: entry.universe,
      shape_matched: entry.shape_matched,
      missing_shape: entry.missing_shape,
      is_metric: entry.is_metric,
    }),
  )

  // The measurable way out of a matched set nobody can read: which config is
  // costing the most on which eval, and what dropping it recovers. Computed
  // only when there is something to recover from - it re-runs the matcher once
  // per basis config, which is cheap but not free, and pointless while every
  // eval is healthy.
  $: basis_recovery = compute_basis_recovery(
    match_result,
    eval_run_index_cache,
    basis_ids,
    match_predicate,
    tool_source,
    is_metric_eval_id,
    eval_names_by_id,
    config_label,
  )
  function compute_basis_recovery(
    result: typeof match_result,
    indexes: RunIndexes,
    ids: string[],
    predicate: MatchPredicate,
    source: ReturnType<typeof tool_call_source>,
    is_metric: (evalId: string) => boolean,
    names: Map<string, string>,
    label_of: (id: string) => string,
  ): BasisRecovery[] {
    if (result.applied === "all") return []
    const worth_asking =
      result.fallback === "shape_too_thin" ||
      result.evals.some(
        (entry) =>
          !entry.is_metric &&
          entry.universe > 0 &&
          entry.matched < MIN_MATCHED_N,
      )
    if (!worth_asking) return []
    return recovery_hints(indexes, ids, predicate, source, is_metric).map(
      (hint) => ({
        name: names.get(hint.evalId) ?? "Eval",
        config: label_of(hint.configId),
        from: hint.from,
        to: hint.to,
      }),
    )
  }
  // The default predicate's N range, over the cells the page actually draws.
  // This is the number that was never on screen: it is what says two configs
  // side by side were measured 11 times and 148 times.
  $: basis_n_range = (() => {
    let min = Infinity
    let max = -Infinity
    for (const id of pinned_ids) {
      for (const n of effective_lens_data.counts.get(id)?.values() ?? []) {
        min = Math.min(min, n)
        max = Math.max(max, n)
      }
    }
    return min <= max ? { min, max } : null
  })()
  $: basis_errors = pinned_ids
    .filter((id) => !!eval_run_index_errors[id])
    .map(
      (id): BasisError => ({
        label: config_label(id),
        message: eval_run_index_errors[id],
      }),
    )
  $: basis_missing_shape_labels =
    match_result.configs_missing_shape.map(config_label)

  // Matched conversations behind the cost/latency numbers, as one phrase. The
  // price/latency card states its lane unconditionally, so under a predicate it
  // has to state the basis too - "$0.31 a conversation" is a different claim
  // over 23 matched conversations than over every run a config ever had.
  // How the charts name the basis in their own subtitles. "Among conversations
  // of similar length" - never "controlled for length", which is a claim these
  // predicates cannot support (see run_matching's header on r = 0.26).
  $: match_basis_phrase =
    match_result.applied === "length"
      ? "similar length, run by every config here"
      : match_result.applied === "tools"
        ? "similar tool use, run by every config here"
        : "run by every config here"

  $: matched_conversation_phrase = (() => {
    if (!matched_usage) return ""
    const counts = visible_pinned_ids
      .map((id) => matched_usage?.get(id)?.n_conversations ?? 0)
      .filter((n) => n > 0)
    if (counts.length === 0) return ""
    const min = Math.min(...counts)
    const max = Math.max(...counts)
    return min === max ? ` (n=${min})` : ` (n=${min}–${max})`
  })()

  // ---- One legend for the charts ------------------------------------------
  // The three plots below - the quality radar, the performance bars, and the
  // parallel-coordinates view of the same quality scores - are one comparison
  // drawn three ways, so the reader gets ONE legend for all of them, above
  // them (evolution_legend.svelte). Each chart used to carry its own echarts
  // legend, keyed by display name and toggled independently: switching a
  // config off to read the radar left it drawn on the two charts underneath.
  //
  // Hiding is subtraction HERE rather than suppression inside a chart. A
  // hidden config simply never reaches one, which is what lets three charts
  // that know nothing about each other stay in step.
  $: reconcile_visibility(pinned_ids)
  $: visible_pinned_ids = visible_ids(pinned_ids, $hidden_run_config_ids)
  // Colour is fixed by position in the PINNED list, not by a chart's series
  // index. Any of the three can drop a config it has no numbers for, and doing
  // so used to renumber the palette for every config after it - so the same
  // run config came out one colour on the radar and another on the bars.
  $: series_colors = series_color_map(pinned_ids)
  // ...and what each one is CALLED, decided here for the same reason: the
  // model leads every label on this page, and whether a config's own name has
  // to follow it depends on the whole pinned set, which only the page knows.
  // Built over every pinned config rather than the visible ones, so hiding a
  // chip in the legend cannot rename the configs still drawn beside it.
  $: pinned_configs = pinned_ids
    .map((id) => (run_configs ?? []).find((config) => config.id === id))
    .filter((config): config is TaskRunConfig => !!config)
  $: series_labels = series_display_map(pinned_configs, $model_info)

  // ---- Hidden rows --------------------------------------------------------
  // One filtered view of the score keys drives both the matrix rows and the
  // radar axes, so the two stay consistent. `lens_data.keyMetas` itself is left
  // whole: the strips, the aggregate lens and the lens dropdown are unaffected.
  $: hidden_score_set = new Set(hidden_scores)
  $: visible_key_metas = lens_data.keyMetas.filter(
    (meta) => !hidden_score_set.has(score_key_id(meta.evalId, meta.scoreKey)),
  )

  // Which usage rollup key each usage table row prints. The rollup reaches the
  // page as one blob rather than as score keys, so this is the only link
  // between a usage ROW and the axis it feeds.
  const USAGE_ROW_METRIC_KEYS: Record<UsageRowKey, string> = {
    cost: COST_KEY,
    tokens: TOTAL_TOKENS_KEY,
    latency: LATENCY_KEY,
  }

  // The hidden rows, as axis keys. A score row's key IS its axis key; a usage
  // row's is the rollup field it prints. See visible_metric_axes for why the
  // metrics radar filters on the built axes rather than on the score keys.
  $: hidden_metric_axis_keys = new Set<string>([
    ...hidden_scores,
    ...USAGE_ROWS.filter((row) => hidden_usage.includes(row.key)).map(
      (row) => USAGE_ROW_METRIC_KEYS[row.key],
    ),
  ])

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

  // Carries the eval id as well as the label, so a hidden row can be offered
  // back by the table it came out of rather than by a menu spanning both - and
  // under the name that table gave it, which is what score_row_label settles.
  // Deriving a label here instead named performance rows for their raw score
  // key, so the menu offered "Latency Ms Turn1" back for a row called "Turn 1
  // Latency": you hid one thing and were offered another.
  //
  // The unresolved case is a key with no meta left, which is a stale URL the
  // moment before validateStateFromURL drops it. There is no track to route on
  // without a meta, so it keeps the plain score-key name.
  $: hidden_score_info = hidden_scores.map((key) => {
    const meta = lens_data.keyMetas.find(
      (candidate) => score_key_id(candidate.evalId, candidate.scoreKey) === key,
    )
    return {
      key,
      eval_id: meta?.evalId ?? key.split("::")[0] ?? "",
      label: meta
        ? `${score_row_label(meta, metric_eval_id_set)} · ${meta.evalName}`
        : score_key_label(key.split("::")[1] ?? key),
    }
  })

  $: hidden_usage_info = hidden_usage.map((key) => ({
    key,
    label: USAGE_ROWS.find((row) => row.key === key)?.label ?? key,
  }))

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

  // ---- Quality families ---------------------------------------------------
  // The grouping the task itself declares, read off its specs. See
  // score_families: it is never invented here, and a task that declares none
  // leaves every derived value below empty, which every consumer reads as
  // "ungrouped" and renders exactly as it did before families existed.
  $: score_families = build_score_families(specs)

  // ...and the other thing the specs are good for: what each criterion
  // actually says. The quality radar shows it when a reader hovers an axis
  // name, which is otherwise a short label with nowhere on the page that
  // explains it. Same best-effort fetch, so a task with no specs simply has no
  // popups. See $lib/utils/evolution/axis_help.
  $: spec_descriptions = spec_descriptions_by_eval(specs)

  // The families actually in play on this track, in ring order. Derived from
  // the criteria on the page rather than from every spec, so a family whose
  // evals have no scores yet does not claim an arc or a table header.
  $: quality_families = order_families(
    criterion_metas.map((meta) => family_for_eval(score_families, meta.evalId)),
  )
  // One family divides nothing, so it is not a grouping
  $: quality_grouped = quality_families.length > 1

  // Sorted family by family, which is what makes a band on the ring an unbroken
  // run and a group in the table contiguous. Informational keys sink within
  // their family rather than to the bottom of everything, so a family's rows
  // stay together.
  //
  // ALWAYS sorted, including when there is only one family and the family rank
  // contributes nothing. The unsorted branch this replaces fell back to the
  // order the metas arrived in, and that order is the order the SERVER's evals
  // dict was built in, which is the order `os.scandir` yielded the eval
  // directories (basemodel.py: scandir, deliberately unsorted, for speed).
  // Directory order is a property of one machine's local filesystem history -
  // when each eval folder happened to be created or deleted - not of the data.
  // So two people on the same commit, following the same shared link, could see
  // the ring's axes in different positions, with no control on the page to
  // explain the difference and nothing in the URL that could carry it. The
  // trailing evalName/scoreKey tiebreak was already there and already total;
  // it just was not reached when a task declared a single family.
  $: ordered_criterion_metas = [...criterion_metas].sort(
    (a, b) =>
      family_rank(
        quality_families,
        family_for_eval(score_families, a.evalId).id,
      ) -
        family_rank(
          quality_families,
          family_for_eval(score_families, b.evalId).id,
        ) ||
      (a.direction === "informational" ? 1 : 0) -
        (b.direction === "informational" ? 1 : 0) ||
      a.evalName.localeCompare(b.evalName) ||
      a.scoreKey.localeCompare(b.scoreKey),
  )

  // Family per data key for the radar's bands. Empty when ungrouped, which the
  // chart reads as "draw no arcs and no key".
  $: quality_axis_families = (() => {
    if (!quality_grouped) return {}
    const families: Record<string, ScoreFamily> = {}
    for (const meta of ordered_criterion_metas) {
      families[score_key_id(meta.evalId, meta.scoreKey)] = family_for_eval(
        score_families,
        meta.evalId,
      )
    }
    return families
  })()

  $: comparison_features = build_features(ordered_criterion_metas)
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

  // Rebuilt when the effective lens data changes so the radar's reactive blocks
  // notice - which is also how a predicate change reaches the chart at all.
  $: get_model_value_raw = make_value_getter(effective_lens_data)
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
  $: radar_metas = ordered_criterion_metas.filter(
    (meta) =>
      meta.direction !== "lower_is_better" &&
      meta.direction !== "informational",
  )
  $: radar_axis_count = radar_metas.length

  // ---- Uncertainty view ---------------------------------------------------
  // The same axes as the radar, in the same order, so the chart below it is
  // the same comparison with its confidence intervals drawn rather than a
  // second, subtly different one. It needs the sample size behind each mean,
  // which the radar never asks for.
  $: parallel_axes = radar_metas.map(
    (meta): ParallelAxisSpec => ({
      key: score_key_id(meta.evalId, meta.scoreKey),
      label: score_key_label(meta.scoreKey),
      evalName: meta.evalName,
      type: meta.type,
    }),
  )
  // Reads the effective data, so the parallel chart's Wilson bands widen with
  // the filtered N without the chart knowing a predicate exists.
  $: get_sample_size = make_sample_size_getter(effective_lens_data)
  function make_sample_size_getter(data: LensData) {
    return (runConfigId: string, dataKey: string): number | null =>
      data.counts.get(runConfigId)?.get(dataKey) ?? null
  }
  $: parallel_available = pinned_nodes.length > 0 && parallel_axes.length >= 2
  $: radar_available =
    pinned_nodes.length > 0 && radar_axis_count >= MIN_RADAR_AXES
  // Hiding every quality row is a different problem from a task with too few
  // higher-is-better scores, and it has a different remedy - the table's own
  // Hidden control. The line below it, that every score is still in the table,
  // is also untrue in that state: the table is empty too, and says so itself.
  $: quality_all_hidden =
    criterion_metas.length === 0 && hidden_quality_info.length > 0

  // ---- Performance metrics on the uncertainty view ------------------------
  // Opt-in extra axes on the parallel chart, so a question that crosses the two
  // tracks ("the config that wins on P1 - what did it cost?") can be read off
  // one picture instead of by matching colours between two.
  //
  // They are RANKS, and everything below exists to keep that honest.
  //
  // A quality axis is plotted as a share of its score's own full range, which
  // works because pass/fail RUNS 0 to 1. A cost has no top and a latency has no
  // top, so there is no fraction to take. Min-max over the configs shown would
  // manufacture one, and would be wrong twice: it pins the best config to
  // exactly 1.0 and the worst to exactly 0.0 on every axis whatever the spread
  // (two configs a hundredth of a cent apart would draw the full height of the
  // axis between them), and one outlier flattens everyone else onto the floor.
  // So each metric is plotted as the config's POSITION among the configs
  // currently drawn - see rank_score for the arithmetic and why it is capped
  // strictly inside (0,1), which is what keeps a rank axis from ever claiming
  // the 0 and 1 that a pass/fail axis earns.
  //
  // "Currently drawn" is `visible_pinned_ids`, and that is the semantics rather
  // than an implementation detail: the scale is the SELECTION. Unpinning a
  // config, or switching one off in the legend, re-ranks every metric axis, and
  // the chart says so on the axis name, in the tooltip and under the header.
  // Nothing else on the page behaves this way, which is exactly why it is said
  // three times.

  // Filtered from the canonical catalog rather than mapped from the selection,
  // so the axes append in chart order however they were switched on - and
  // through `visible_axes`, so hiding a performance row takes its rank axis off
  // this chart too. That is what the x on a table row means everywhere else on
  // the page (it leaves the table AND the chart beside it), and a metric that
  // is out of the comparison cannot be a legitimate axis on a chart of that
  // comparison.
  $: parallel_metric_axes = visible_axes.filter((axis) =>
    parallel_metric_keys.includes(axis.key),
  )

  // One rank map per added metric, over exactly the configs the chart draws.
  // Rebuilt whenever the pins, the legend, the selection or the underlying
  // numbers move - all four are arguments, so none of them can change without
  // the ranks being recomputed.
  $: parallel_rank_scores = build_parallel_rank_scores(
    parallel_metric_axes,
    visible_pinned_ids,
    get_metric_value,
  )
  function build_parallel_rank_scores(
    axes: MetricAxis[],
    run_config_ids: string[],
    getter: (run_config_id: string, key: string) => number | null,
  ): Record<string, Map<string, number | null>> {
    const ranks: Record<string, Map<string, number | null>> = {}
    for (const axis of axes) {
      ranks[axis.key] = capped_rank_scores(
        run_config_ids.map((id) => ({ id, value: getter(id, axis.key) })),
        // The catalog's own direction, so UP is BETTER on a rank axis exactly
        // as it is on every quality axis beside it
        axis.better,
      )
    }
    return ranks
  }

  $: get_parallel_rank_score = make_rank_score_getter(parallel_rank_scores)
  function make_rank_score_getter(
    ranks: Record<string, Map<string, number | null>>,
  ) {
    return (run_config_id: string, key: string): number | null =>
      ranks[key]?.get(run_config_id) ?? null
  }

  // An added metric that no visible config has a number for. Dropped rather
  // than drawn as an empty column: a rank axis with nothing on it is not an
  // axis, and leaving it in place would spend width on a line whose only
  // reading - "these configs all rank the same here" - is false. Named in the
  // footnote instead, so the reader is told where their metric went.
  $: parallel_metric_plotted = parallel_metric_axes.filter((axis) =>
    visible_pinned_ids.some(
      (id) => parallel_rank_scores[axis.key]?.get(id) != null,
    ),
  )
  $: parallel_metric_empty = parallel_metric_axes.filter(
    (axis) => !parallel_metric_plotted.includes(axis),
  )
  // ...and one an active selection points at, but whose row was hidden from the
  // performance table. Its axis is gone for a different reason and has a
  // different remedy, so it is counted separately rather than folded in above.
  $: parallel_metric_hidden_count = parallel_metric_keys.filter(
    (key) =>
      !visible_axes.some((axis) => axis.key === key) &&
      all_metric_axes.some((axis) => axis.key === key),
  ).length

  $: parallel_metrics_note = (() => {
    const parts: string[] = []
    if (parallel_metric_empty.length > 0) {
      // Under a predicate the absence is attributable: the metric is not
      // missing, the conversations it would have been read over are. Saying
      // "no values" there would read as "this config was never run".
      parts.push(
        `${
          matching_active
            ? "No matched conversations on the configs shown"
            : "No values on the configs shown"
        }: ${parallel_metric_empty.map((axis) => axis.valueLabel).join(", ")}.`,
      )
    }
    if (parallel_metric_hidden_count > 0) {
      parts.push(
        `${parallel_metric_hidden_count} added ${
          parallel_metric_hidden_count === 1 ? "metric is" : "metrics are"
        } hidden from the comparison — restore from “Hidden” above the performance table.`,
      )
    }
    return parts.length > 0 ? parts.join(" ") : null
  })()

  // The axis set the chart actually receives: the radar's quality axes first,
  // the rank axes appended. Order past that point is the reader's - the chart's
  // own drag handles own it, and reconcile_order keeps an arrangement across a
  // metric being switched on or off.
  $: parallel_chart_axes = [
    ...parallel_axes,
    ...parallel_metric_plotted.map(
      (axis): ParallelAxisSpec => ({
        key: axis.key,
        label: axis.label,
        // The axis is named for the virtue ("Cost Efficiency"), so the line
        // under it names the quantity and where it came from - the same
        // subtitle the metrics picker and the bar chart's tooltips print.
        evalName: `${axis.valueLabel} · ${axis.evalName ?? "Usage rollup"}`,
        // No score type: a metric has no rating scale, which is the whole
        // reason it is ranked instead of scaled.
        type: null,
        rank: true,
        format: (value: number | null) => format_metric_value(axis.unit, value),
      }),
    ),
  ]

  // The picker on the parallel card. Built like the performance track's Metrics
  // menu and grouped the same way, because it IS the same choice made against
  // the same catalog - one control the reader has already learned. The counts
  // read "on out of available", which is 0 of n everywhere until they add one.
  $: parallel_metric_menu_items = (() => {
    const items: FloatingMenuItem[] = []
    let family: MetricFamily | null = null
    for (const axis of visible_axes) {
      if (axis.family !== family) {
        family = axis.family
        const in_family = visible_axes.filter(
          (candidate) => candidate.family === family,
        )
        const on_in_family = in_family.filter((candidate) =>
          parallel_metric_keys.includes(candidate.key),
        ).length
        items.push({
          label: `${METRIC_FAMILY_LABELS[family]} · ${on_in_family} of ${in_family.length}`,
          header: true,
        })
      }
      const on = parallel_metric_keys.includes(axis.key)
      items.push({
        label: `${on ? "✓" : "+"}  ${axis.label}`,
        description: `${axis.valueLabel} · ${axis.evalName ?? "Usage rollup"}`,
        onclick: () => toggle_parallel_metric_axis(axis.key),
      })
    }
    if (parallel_metric_keys.length > 0) {
      items.push({
        label: "Clear metric axes",
        onclick: () => (parallel_metric_keys = []),
      })
    }
    return items
  })()

  function toggle_parallel_metric_axis(key: string) {
    // Resolved against the UNFILTERED catalog for the same reason the sibling
    // picker is: an axis whose row is hidden is not in `visible_axes`, and
    // dropping it here would edit the selection as a side effect of an
    // unrelated click.
    parallel_metric_keys = toggled_metric_axis_keys(
      all_metric_axes,
      parallel_metric_keys,
      key,
    )
  }

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
    get_metric_value_unfiltered,
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
  // Everything the reader sees is filtered through this; the catalog above
  // stays whole, and is what the default set and a saved selection resolve
  // against. See visible_metric_axes.
  $: visible_axes = visible_metric_axes(
    all_metric_axes,
    hidden_metric_axis_keys,
  )
  // What hiding took off the ring, as a count. The chart's empty state has to
  // name a control that can give an axis back, and for a hidden row the Axes
  // menu is not it - it does not offer one.
  $: hidden_axis_count = all_metric_axes.length - visible_axes.length
  $: default_metric_keys = default_metric_axis_keys(all_metric_axes)
  $: shown_metric_keys = metric_axis_keys ?? default_metric_keys
  // Filtered from the canonical list rather than mapped from the selection, so
  // the axis order is stable no matter what order they were switched on in.
  $: shown_metric_axes = visible_axes.filter((axis) =>
    shown_metric_keys.includes(axis.key),
  )

  function toggle_metric_axis(key: string) {
    metric_axis_keys = toggled_metric_axis_keys(
      all_metric_axes,
      shown_metric_keys,
      key,
    )
  }

  function reset_metric_axes() {
    metric_axis_keys = null
  }

  // Grouped under the same family headings the chart lays the metrics out by,
  // so the menu reads down in the chart's own order. The heading counts what is ON
  // out of what exists, which is the number the chart's own family key shows -
  // "Tokens 3" under the title is these three ticks.
  $: metric_menu_items = (() => {
    const items: FloatingMenuItem[] = []
    let family: MetricFamily | null = null
    // Over the visible axes: a hidden row is not an axis the reader can turn
    // on, so counting it as available would make every "x of y" overstate what
    // the menu offers.
    for (const axis of visible_axes) {
      if (axis.family !== family) {
        family = axis.family
        const in_family = visible_axes.filter(
          (candidate) => candidate.family === family,
        )
        const shown_in_family = in_family.filter((candidate) =>
          shown_metric_keys.includes(candidate.key),
        ).length
        items.push({
          label: `${METRIC_FAMILY_LABELS[family]} · ${shown_in_family} of ${in_family.length}`,
          header: true,
        })
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
  // has no better end at all, and a bar can only say "longer is better".
  $: metrics_not_shown_note = (() => {
    const parts: string[] = []
    // Against the visible axes, not the catalog: a hidden row was not "not
    // selected", it was taken out of the comparison, and the table's own
    // "Hidden (n)" control is what states that and offers it back.
    const off = visible_axes.length - shown_metric_axes.length
    if (off > 0) {
      parts.push(`${off} ${off === 1 ? "metric" : "metrics"} not selected`)
    }
    const directionless = directionless_key_count(visible_key_metas)
    if (directionless > 0) {
      parts.push(
        `${directionless} ${
          directionless === 1 ? "score" : "scores"
        } with no better direction`,
      )
    }
    return parts.length > 0 ? parts.join(", ") : null
  })()

  // ---- Comparison tables --------------------------------------------------
  // Two tables, one per track, split by exactly the rule the two radars use -
  // `is_metric_eval`, via metric_eval_ids - so a score can never appear on one
  // chart and in the other track's table.
  //
  // Row labels are the one place the two tracks have to say different things.
  // The metrics RADAR names an axis for the virtue, because the geometry
  // already claims further-is-better and the label has to agree with it; a
  // TABLE prints the raw number, where higher is usually worse, so "Total
  // Latency 42,423.91 ms" under a heading reading "Speed" would contradict the
  // row. The table therefore takes the plain quantity name - metric_row_info,
  // the same choice the chart's own tooltips make. The family HEADINGS are
  // shared between chart and table, and can be: "Tokens" and "Speed" name a
  // subject, they do not claim which end is good.
  //
  // The quality track needs none of that: a pass rate is higher-is-better in
  // both places, so its rows keep the score key's own name.
  //
  // That rule lives in score_row_label rather than in each table, because the
  // Hidden menus have to name a row the way the table that hid it did.

  $: metric_eval_id_set = metric_eval_ids(lens_data.keyMetas)

  function score_sublabel(meta: ScoreKeyMeta): string {
    return meta.direction === "informational"
      ? `${meta.evalName} · informational`
      : meta.evalName
  }

  /** Rows in the order given, cut into contiguous groups by family */
  function group_rows(
    rows: { row: MatrixRow; family: string; label: string | null }[],
  ): MatrixGroup[] {
    const groups: MatrixGroup[] = []
    for (const entry of rows) {
      const open = groups[groups.length - 1]
      if (open && open.key === entry.family) {
        open.rows.push(entry.row)
        continue
      }
      groups.push({
        key: entry.family,
        label: entry.label,
        rows: [entry.row],
      })
    }
    return groups
  }

  $: quality_table_groups = group_rows(
    ordered_criterion_metas.map((meta) => {
      const family = family_for_eval(score_families, meta.evalId)
      return {
        family: quality_grouped ? family.id : "all",
        label: quality_grouped ? family.label : null,
        row: {
          kind: "score" as const,
          meta,
          label: score_row_label(meta, metric_eval_id_set),
          sublabel: score_sublabel(meta),
        },
      }
    }),
  )

  // The performance track: every metric score key plus the native usage
  // rollup, interleaved into one list ordered by the metrics catalog's own
  // families. The rollup rows land inside Cost, Tokens and Speed rather than
  // stranded under everything else, which is where they were.
  $: performance_table_groups = (() => {
    const entries: {
      row: MatrixRow
      family: MetricFamily
      label: string
    }[] = []

    for (const meta of visible_key_metas) {
      if (!metric_eval_id_set.has(meta.evalId)) continue
      const family = metric_row_info(meta.scoreKey).family
      entries.push({
        family,
        label: METRIC_FAMILY_LABELS[family],
        row: {
          kind: "score",
          meta,
          label: score_row_label(meta, metric_eval_id_set),
          sublabel: score_sublabel(meta),
        },
      })
    }

    for (const usage_row of USAGE_ROWS) {
      if (hidden_usage.includes(usage_row.key)) continue
      const family = usage_row_family(USAGE_ROW_METRIC_KEYS[usage_row.key])
      entries.push({
        family,
        label: METRIC_FAMILY_LABELS[family],
        row: {
          kind: "usage",
          key: usage_row.key,
          label: usage_row.label,
          sublabel: "Usage rollup",
        },
      })
    }

    // Family order first, then the rollup ahead of the eval scores measuring
    // the same family, then by name - so the ordering is a pure function of the
    // rows and never depends on the order the summary listed its evals in.
    entries.sort(
      (a, b) =>
        METRIC_FAMILIES.indexOf(a.family) - METRIC_FAMILIES.indexOf(b.family) ||
        (a.row.kind === "usage" ? 0 : 1) - (b.row.kind === "usage" ? 0 : 1) ||
        a.row.label.localeCompare(b.row.label),
    )

    return group_rows(
      entries.map((entry) => ({
        row: entry.row,
        family: entry.family,
        // Always grouped: unlike the quality families these come from a
        // catalog this repo owns, so the headings always exist
        label: entry.label,
      })),
    )
  })()

  // Hidden rows belong to whichever table they came out of, so each table
  // carries its own restore control rather than one shared menu offering to
  // restore a row into the other table.
  $: hidden_quality_info = hidden_score_info.filter(
    (info) => !metric_eval_id_set.has(info.eval_id),
  )
  $: hidden_performance_info = hidden_score_info.filter((info) =>
    metric_eval_id_set.has(info.eval_id),
  )

  function hidden_menu(
    scores: { key: string; label: string }[],
    usage: { key: string; label: string }[],
  ): FloatingMenuItem[] {
    return [
      ...(scores.length > 0
        ? [
            { label: "Show Score", header: true },
            ...scores.map(
              (info): FloatingMenuItem => ({
                label: info.label,
                onclick: () => show_score_row(info.key),
              }),
            ),
          ]
        : []),
      ...(usage.length > 0
        ? [
            { label: "Show Metric", header: true },
            ...usage.map(
              (info): FloatingMenuItem => ({
                label: info.label,
                onclick: () => show_usage_row(info.key),
              }),
            ),
          ]
        : []),
      ...(scores.length + usage.length > 1
        ? [
            {
              label: "Restore all",
              onclick: () => {
                for (const info of scores) show_score_row(info.key)
                for (const info of usage) show_usage_row(info.key)
              },
            },
          ]
        : []),
    ] as FloatingMenuItem[]
  }

  $: quality_hidden_menu_items = hidden_menu(hidden_quality_info, [])
  $: performance_hidden_menu_items = hidden_menu(
    hidden_performance_info,
    hidden_usage_info,
  )

  // Score keys come from the lens; the usage rollup comes from the lazily
  // fetched per-config summary, or - under a matching predicate - from the
  // matched rollup, so the cost and speed axes are over the same conversations
  // the quality axes are. All three sources are passed in as arguments so the
  // getter is rebuilt (and the charts redrawn) when any of them arrives.
  $: get_metric_value = make_metric_value_getter(
    effective_lens_data,
    eval_scores_cache,
    matched_usage,
  )
  // The same getter over UNFILTERED data, for deciding which axes the catalog
  // has at all. build_metric_axes uses "has a value" to settle which SOURCE
  // wins a quantity (the usage rollup or an eval's own cost_usd key), so
  // feeding it filtered values would let a predicate silently re-point an axis
  // - a different number under an unchanged label. What is IN the comparison is
  // a property of the task; what the numbers are is where the predicate acts.
  $: get_metric_value_unfiltered = make_metric_value_getter(
    lens_data,
    eval_scores_cache,
    null,
  )
  function make_metric_value_getter(
    data: LensData,
    cache: Record<string, RunConfigEvalScoresSummary>,
    matched: Map<string, MatchedUsage> | null,
  ) {
    return (run_config_id: string, key: string): number | null => {
      if (!key.startsWith(USAGE_KEY_PREFIX)) {
        return data.raw.get(run_config_id)?.get(key) ?? null
      }
      if (matched) {
        const usage = matched.get(run_config_id)
        if (!usage) {
          return null
        }
        switch (key) {
          case COST_KEY:
            return usage.mean_cost
          case TOTAL_TOKENS_KEY:
            return usage.mean_total_tokens
          case LATENCY_KEY:
            return usage.mean_latency_ms
          case INPUT_TOKENS_KEY:
            return usage.mean_input_tokens
          case OUTPUT_TOKENS_KEY:
            return usage.mean_output_tokens
          default:
            return null
        }
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

  // What the matrices' usage rows print. Null keeps them on the native rollup,
  // which is what they have always shown.
  $: matrix_usage_getter = matched_usage
    ? (run_config_id: string, key: UsageRowKey): number | null => {
        const usage = matched_usage?.get(run_config_id)
        if (!usage) return null
        switch (key) {
          case "cost":
            return usage.mean_cost
          case "tokens":
            return usage.mean_total_tokens
          case "latency":
            return usage.mean_latency_ms
        }
      }
    : null

  // ---- Price vs latency ---------------------------------------------------
  // The one chart on this page whose question is "which of these do we ship".
  // It needs a single number for quality, and that number is the WEAKEST
  // CONCERN AREA rather than the mean of every criterion - see quality_score.
  // A mean lets a config buy back a failure on the criterion the customer
  // cares most about with a pass on one nobody was worried about, which is how
  // an arm cleared a 70% gate with a 48% write-correctness coin flip inside it.
  //
  // Computed off effective_lens_data, so it recomputes over the matched
  // conversations under a predicate with nothing else to do, and off the same
  // family grouping the radar's bands read (score_families). Read straight
  // from the lens rather than through `current_lens`, because the gate is not
  // a lens - a reader looking at one criterion on the graph has not said they
  // want their shipping decision made on that one criterion.
  $: quality_breakdowns = build_quality_breakdowns(
    effective_lens_data,
    score_families,
    pinned_ids,
  )
  function build_quality_breakdowns(
    data: LensData,
    families: Map<string, ScoreFamily>,
    ids: string[],
  ): Map<string, QualityBreakdown | null> {
    return new Map(
      ids.map((id) => [id, weakest_family_quality(data, families, id)]),
    )
  }
  $: get_quality_breakdown = (run_config_id: string): QualityBreakdown | null =>
    quality_breakdowns.get(run_config_id) ?? null
  $: get_quality = make_quality_getter(quality_breakdowns)
  function make_quality_getter(
    breakdowns: Map<string, QualityBreakdown | null>,
  ) {
    return (run_config_id: string): number | null =>
      breakdowns.get(run_config_id)?.quality ?? null
  }
  // Whether the number is a weakest area or the flat mean, which is what the
  // gate menu and the chart have to call it. Taken from whatever the pinned
  // configs resolved to: the grouping is a property of the task, so they agree.
  $: quality_is_grouped = [...quality_breakdowns.values()].some(
    (breakdown) => breakdown?.mode === "families",
  )

  // The gate the reader can set. Round numbers, not a slider: the floor is an
  // argument ("80% is good enough to ship"), and an argument is made in round
  // numbers. A slider would also invite tuning the gate until the preferred
  // config is the only one left, which is the one thing this chart must not
  // make easy.
  //
  // The numbers on offer come from the DATA, not from a fixed ladder. A menu of
  // 50/70/80/90 is a claim about where quality lands on a task, and it was
  // wrong on the first real one: five configs between 51% and 64% meant 50%
  // gated out nobody and 70/80/90 gated out everybody - four positions, none of
  // which drew a different chart. The quintiles of the plotted configs' quality
  // always cut BETWEEN them. See quality_gate_cuts for the rule that decides
  // which of the four earn a row.
  $: quality_floor_label =
    quality_floor === null ? "Off" : `${Math.round(quality_floor * 100)}%`

  // What each floor would leave standing, so the reader can see what a gate
  // costs them before setting it rather than by trying all of them. The same
  // pure functions the chart draws from, over the same inputs, so the menu
  // cannot disagree with the picture beside it.
  $: price_latency_plotted = build_price_latency_points(
    visible_pinned_ids,
    get_metric_value,
    get_quality,
  ).plotted
  // Only the configs actually ON the plane feed the cuts - a config with no
  // cost has no dot to gate. The getter is whatever the page calls quality
  // today; the cuts take the numbers and ask nothing about where they came
  // from.
  $: quality_gate_cut_values = quality_gate_cuts(
    price_latency_plotted.map((point) => point.quality),
  )
  $: quality_scored_count = price_latency_plotted.filter(
    (point) => point.quality !== null,
  ).length
  // Why the menu is Off-only, in the words of the data that made it so.
  $: no_gate_cuts_reason =
    quality_scored_count < 2
      ? `Only ${quality_scored_count} of these has a quality score, so there is nothing to cut between.`
      : "Every scored config here is at the same quality, so any gate would keep all of them or none."
  // A floor from a shared link that no current cut matches still applies - the
  // gate travelled with the argument someone sent, and dropping it would change
  // their chart out from under them. It gets its own row so the menu shows a
  // checked option rather than four unchecked ones over a gated chart.
  $: custom_quality_floor = floor_off_the_menu(
    quality_floor,
    quality_gate_cut_values,
  )
  function floor_off_the_menu(
    floor: number | null,
    cuts: number[],
  ): number | null {
    if (floor === null) return null
    // Both sides are whole percents by construction, so this is an equality
    // test written to survive the float arithmetic that produced them.
    return cuts.some((cut) => Math.abs(cut - floor) < 1e-9) ? null : floor
  }
  // What the gate MEANS, stated in the menu that sets it. Under families the
  // floor is non-compensatory - every area has to clear it, not the average -
  // and that is the whole difference between this gate and the one it replaced.
  // A task with no family grouping gets the old sentence, because that is what
  // its number still is.
  $: quality_gate_header = quality_is_grouped
    ? `Quality gate: every area ≥ ${quality_floor === null ? "the floor" : quality_floor_label}`
    : "Quality gate"
  $: quality_gate_hint = quality_is_grouped
    ? "Only configs whose weakest concern area clears this floor are compared on price"
    : "Only configs at or above this aggregate quality are compared on price"
  $: quality_floor_menu_items = [
    { label: quality_gate_header, header: true },
    {
      // A marker on every row, not just the chosen one: the labels are rendered
      // as ordinary text, where a leading run of spaces collapses to one, so an
      // unmarked row would sit a glyph to the left of its neighbours.
      label: `${quality_floor === null ? "✓" : "○"}  Off`,
      description:
        quality_gate_cut_values.length === 0
          ? `Compare all ${price_latency_plotted.length} plotted on price and speed. ${no_gate_cuts_reason}`
          : `Compare all ${price_latency_plotted.length} plotted on price and speed`,
      onclick: () => set_quality_floor(null),
    },
    ...quality_gate_cut_values.map((floor) => ({
      label: `${quality_floor === floor ? "✓" : "○"}  ${Math.round(floor * 100)}%`,
      description: `${
        split_by_gate(price_latency_plotted, floor).qualifying.length
      } of ${price_latency_plotted.length} clear it`,
      onclick: () => set_quality_floor(floor),
    })),
    ...(custom_quality_floor === null
      ? []
      : [
          {
            label: `✓  Custom: ${Math.round(custom_quality_floor * 100)}%`,
            description: `${
              split_by_gate(price_latency_plotted, custom_quality_floor)
                .qualifying.length
            } of ${price_latency_plotted.length} clear it — from the link this page was opened with`,
            onclick: () => set_quality_floor(custom_quality_floor),
          },
        ]),
  ] as FloatingMenuItem[]

  // Through a function rather than assigned in the menu block above: the menu
  // now READS a value derived from the floor (the custom row), and a reactive
  // block that both reads that derivation and writes the floor is a cycle the
  // Svelte compiler rejects. The write is the same one either way.
  function set_quality_floor(floor: number | null) {
    quality_floor = floor
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
            label: "No score",
            value: "none",
            description: "Run counts and per-eval deltas only",
          },
          {
            label: "Aggregate score",
            value: "aggregate",
            // Named as what it is. Every eval counts the same in it, which is
            // a claim about the task that nothing in the task supports.
            description: "Unweighted mean of all normalized eval scores",
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
        runs: node.ghost ? 0 : run_count(data, node.id),
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
      <!-- The dataset split every score and metric on this page is read over.
           One control for the whole page, not one per card: quality from the
           test set beside cost from train would be a number nobody could act
           on. "All runs" is every eval run that exists, which is the only view
           that includes runs against items that have since left their split. -->
      <div class="flex flex-row items-center gap-2">
        <div class="join" role="group" aria-label="Dataset split">
          {#each SPLIT_VIEWS as split_option}
            <button
              type="button"
              class="join-item btn btn-sm font-normal {split_view ===
              split_option
                ? 'btn-active'
                : ''}"
              aria-pressed={split_view === split_option}
              on:click={() => (split_view = split_option)}
            >
              {SPLIT_LABELS[split_option]}
            </button>
          {/each}
        </div>
        {#if summary_refreshing}
          <span class="loading loading-spinner loading-xs text-gray-400"></span>
        {:else if split_coverage}
          <span class="text-xs text-gray-500">
            {split_coverage.missing} of {split_coverage.total} evals have no {SPLIT_LABELS[
              split_view
            ].toLowerCase()} set
          </span>
        {/if}
      </div>
      <!-- Which conversations the pinned configs are compared ON. One control
           for the whole page, beside the split for the same reason: the charts
           are one comparison drawn several ways, and a radar over matched runs
           above a table over pooled ones is a lie of composition. See
           run_matching for what each option does and, more importantly, what
           the shape ones are not. -->
      <div class="flex flex-row items-center gap-2">
        <span class="text-sm text-gray-500">Matching:</span>
        <div class="join" role="group" aria-label="Run matching">
          {#each MATCH_PREDICATES as predicate_option}
            <button
              type="button"
              class="join-item btn btn-sm font-normal {match_predicate ===
              predicate_option
                ? 'btn-active'
                : ''}"
              aria-pressed={match_predicate === predicate_option}
              on:click={() => (match_predicate = predicate_option)}
            >
              {MATCH_LABELS[predicate_option]}
            </button>
          {/each}
        </div>
      </div>
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

    <!-- One legend for everything under it. Above the charts rather than
         inside any of them: it governs all three, and a control that belongs
         to three things cannot live in one of them. See evolution_legend.

         Mounted bare, with no wrapper: it is sticky, and a sticky box travels
         inside its containing block, so a div wrapped tight around it would pin
         it to a 100px-tall box and it would never move. Its containing block is
         this page body instead, which is why it stays on screen for the whole
         comparison. It carries its own top margin as padding for the same
         reason - see the component. -->
    <EvolutionLegend
      run_configs={run_configs ?? []}
      {pinned_ids}
      model_info={$model_info}
      {prompts}
      colors={series_colors}
    />

    <!-- What every number under here is over. Between the legend and the
         charts because it governs all of them, and rendered at every
         predicate - including the default, where the fact worth stating is
         that the configs are NOT on the same conversations. -->
    {#if pinned_nodes.length > 0}
      <div class="mt-3">
        <ComparisonBasis
          applied={match_result.applied}
          requested={match_predicate}
          fallback={match_result.fallback}
          basis_count={basis_ids.length}
          evals={basis_evals}
          n_range={basis_n_range}
          missing_shape_labels={basis_missing_shape_labels}
          tool_source_available={tool_source !== null}
          errors={basis_errors}
          recovery={basis_recovery}
          loading={matching_pending}
        />
      </div>
    {/if}

    <!-- Section 2: the two charts, side by side - quality on the left, what it
         cost to get it on the right. They only pair up once there is room for
         the radar's ring plus its axis names and the bars plus their gutter
         (each needs roughly 540px before the plot starts losing to the
         labels), so below xl they stack and each one is page-width again.

         Height is what both charts grow into - a radius for one, a row per
         metric for the other - so the floor is generous: the chart's own 640px
         box plus its card header and padding. Tall enough for wrapped axis
         names all the way round the outer ring and, when a reader switches
         more on, about a dozen readable metric rows - well past the five the
         chart opens with. Neither carries a legend of its own any more - the page's is
         above - so all of that box is plot.

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
            selectedRunConfigIds={visible_pinned_ids}
            seriesColors={series_colors}
            seriesLabels={series_labels}
            external_legend={true}
            scoreAxisMaxes={score_axis_maxes}
            scoreDirections={score_directions}
            axisFamilies={quality_axis_families}
            specDescriptions={spec_descriptions}
            getSampleSize={get_sample_size}
            title="Quality Scores"
            subtitle={`Eval scores for the selected run configurations.${
              split_scope_label ? ` ${split_scope_label} only.` : ""
            }${
              matching_active
                ? ` Among conversations of ${match_basis_phrase}.`
                : ""
            } Higher is better on every axis.`}
            table_location="below"
            legend_position="bottom"
          />
        {:else}
          <div
            class="flex-1 bg-white border border-gray-200 rounded-lg p-6 flex flex-col justify-center items-center text-center"
          >
            <div class="text-lg font-medium text-gray-900 mb-1">
              {#if pinned_nodes.length === 0}
                Pin configs to compare
              {:else if quality_all_hidden}
                Every quality score is hidden
              {:else}
                Not enough scores to plot
              {/if}
            </div>
            <div class="text-sm text-gray-500 max-w-md">
              {#if pinned_nodes.length === 0}
                Select a run config, or hover a card and hit Pin, to build a
                compare set. Up to {MAX_PINS} configs are charted here and listed
                in the table below.
              {:else if quality_all_hidden}
                Every quality score is hidden from this comparison. Use “Hidden”
                above the table below to restore them.
              {:else if hidden_quality_info.length > 0}
                A radar chart needs at least {MIN_RADAR_AXES} higher-is-better scores.
                Some are hidden — use “Hidden” above the table below to restore them.
              {:else}
                A radar chart needs at least {MIN_RADAR_AXES} higher-is-better scores.
                Every score is still in the comparison table below.{#if matching_active}
                  Matching is on — switch it back to “{MATCH_LABELS.all}” above
                  to compare on every run instead.{/if}
              {/if}
            </div>
          </div>
        {/if}
      </div>

      <div class="min-w-0 min-h-[800px] flex flex-col">
        <CompareMetricsBarChart
          scopeLabel={matching_active ? stated_scope_label : split_scope_label}
          axes={shown_metric_axes}
          getMetricValue={get_metric_value}
          getSampleSize={get_sample_size}
          run_configs={run_configs ?? []}
          model_info={$model_info}
          selectedRunConfigIds={visible_pinned_ids}
          seriesColors={series_colors}
          seriesLabels={series_labels}
          notShownNote={metrics_not_shown_note}
          availableAxisCount={visible_axes.length}
          hiddenAxisCount={hidden_axis_count}
        >
          <FloatingMenu slot="controls" items={metric_menu_items} width="w-64">
            <button
              slot="trigger"
              type="button"
              class="btn btn-sm font-normal"
              title="Choose which metrics are plotted"
            >
              Metrics ({shown_metric_axes.length})
            </button>
          </FloatingMenu>
        </CompareMetricsBarChart>
      </div>
    </div>

    <!-- Section 2a: the shipping decision. Quality held to a floor, then the
         two costs that are left - money and time - against each other.

         On its own row under the pair above rather than beside them: it is not
         a third view of the same comparison, it is the question the other two
         are read in service of. It sits ABOVE the confidence view because that
         one is a footnote to the radar directly over it, and splitting the pair
         would break that read.

         HALF WIDTH, in the same two-column grid the radar and bars use, and
         left-aligned in it. A scatter of a dozen dots at most is not a chart
         that grows with the page: stretched across the full width it reads as
         one long empty band with a handful of marks in it, and the eye has to
         travel the whole page to compare two points that are a thumb apart. The
         right column is deliberately empty - the grid is the page's unit of
         layout, so a card that wants half the width takes a column rather than
         a max-width of its own, and whatever lands beside it later inherits a
         row that already lines up. Below xl the grid collapses to one column
         and this is page-width again, exactly like the pair above.

         Mounted whenever anything is pinned, not only when it can draw: the
         card's footnote names the configs it had to leave off and why, and that
         is most worth saying exactly when there is no chart. -->
    {#if pinned_nodes.length > 0}
      <div class="mt-6 grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div class="min-w-0 flex flex-col">
          <ComparePriceLatencyChart
            run_configs={run_configs ?? []}
            model_info={$model_info}
            selectedRunConfigIds={visible_pinned_ids}
            seriesColors={series_colors}
            seriesLabels={series_labels}
            getMetricValue={get_metric_value}
            getQuality={get_quality}
            getQualityBreakdown={get_quality_breakdown}
            getSampleSize={get_sample_size}
            qualityFloor={quality_floor}
            scopeLabel={stated_scope_label}
          >
            <FloatingMenu
              slot="controls"
              items={quality_floor_menu_items}
              width="w-72"
            >
              <button
                slot="trigger"
                type="button"
                class="btn btn-sm font-normal"
                title={quality_gate_hint}
              >
                Quality gate: {quality_floor_label}
              </button>
            </FloatingMenu>
          </ComparePriceLatencyChart>
        </div>
      </div>
    {/if}

    <!-- Section 2b: the quality scores once more, full width, with the
         confidence interval behind each one drawn.

         Under the radar rather than beside it, and full width, because it is
         the same comparison seen a second way rather than a different subject:
         a reader takes the shape off the radar, then comes here to find out
         whether that shape survives its own error bars. Width is what the bands
         need - they are vertical, and squeezing five axes into half the page
         stacks them into mud. -->
    {#if parallel_available}
      <div class="mt-6">
        <!-- get_metric_value is a superset of get_model_value_raw: for every
             key that is not a `cost::` rollup field it reads the same lens map,
             so one getter serves both the quality axes and the raw values
             behind the rank axes. -->
        <CompareParallelChart
          axes={parallel_chart_axes}
          getValue={get_metric_value}
          getSampleSize={get_sample_size}
          getRankScore={get_parallel_rank_score}
          notShownNote={parallel_metrics_note}
          run_configs={run_configs ?? []}
          model_info={$model_info}
          selectedRunConfigIds={visible_pinned_ids}
          seriesColors={series_colors}
          seriesLabels={series_labels}
        >
          <FloatingMenu
            slot="controls"
            items={parallel_metric_menu_items}
            width="w-64"
          >
            <button
              slot="trigger"
              type="button"
              class="btn btn-sm font-normal"
              title="Add a performance metric as a ranked axis on this chart"
            >
              Metrics ({parallel_metric_keys.length})
            </button>
          </FloatingMenu>
        </CompareParallelChart>
      </div>
    {/if}

    <!-- Section 3: the comparison tables - one per track, each full page
         width and stacked rather than paired into columns. There can be a
         dozen run configs, and every one of them is a column: splitting the
         page in two would halve the columns visible before the reader has to
         scroll, in a layout whose whole problem is horizontal room. Each
         table scrolls inside its own container, so the page body never does.

         Same partition as the two radars above (is_metric_eval), so a score
         cannot appear on one chart and in the other track's table.

         Both tables list every PINNED config, including ones switched off in
         the legend above: hiding a config there is decluttering an image, not
         a statement that its numbers are no longer wanted. Flipping
         respect_visibility to true on both is what links them. -->
    {#if pinned_nodes.length > 0}
      <div class="mt-6">
        <div class="flex items-center gap-2 mb-2">
          <div class="text-sm font-medium text-gray-900">
            Quality Scores ({pinned_nodes.length}
            {pinned_nodes.length === 1 ? "config" : "configs"})
          </div>
          {#if hidden_quality_info.length > 0}
            <FloatingMenu items={quality_hidden_menu_items} width="w-72">
              <button
                slot="trigger"
                type="button"
                class="btn btn-xs btn-outline rounded-full font-normal"
                title="Rows hidden from this table and the quality radar"
              >
                Hidden ({hidden_quality_info.length})
              </button>
            </FloatingMenu>
          {/if}
        </div>
        <CompareMatrix
          {pinned_nodes}
          lens_data={effective_lens_data}
          {eval_scores_cache}
          {eval_scores_loading}
          get_usage_value={matrix_usage_getter}
          groups={quality_table_groups}
          respect_visibility={false}
          empty_message="Every quality score is hidden. Use “Hidden” above to restore them."
          on:select={(event) => handle_select(event.detail)}
          on:inspect={(event) =>
            open_inspector(event.detail.eval_id, event.detail.run_config_id)}
          on:hide_score={(event) => hide_score_row(event.detail)}
          on:hide_usage={(event) => hide_usage_row(event.detail)}
        />
      </div>

      <div class="mt-6">
        <div class="flex items-center gap-2 mb-2">
          <div class="text-sm font-medium text-gray-900">
            Performance Metrics ({pinned_nodes.length}
            {pinned_nodes.length === 1 ? "config" : "configs"})
          </div>
          {#if hidden_performance_info.length + hidden_usage_info.length > 0}
            <FloatingMenu items={performance_hidden_menu_items} width="w-72">
              <button
                slot="trigger"
                type="button"
                class="btn btn-xs btn-outline rounded-full font-normal"
                title="Rows hidden from this table and the metrics radar"
              >
                Hidden ({hidden_performance_info.length +
                  hidden_usage_info.length})
              </button>
            </FloatingMenu>
          {/if}
        </div>
        <CompareMatrix
          {pinned_nodes}
          lens_data={effective_lens_data}
          {eval_scores_cache}
          {eval_scores_loading}
          get_usage_value={matrix_usage_getter}
          groups={performance_table_groups}
          respect_visibility={false}
          empty_message="Every performance metric is hidden. Use “Hidden” above to restore them."
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
      declared_splits={summary?.evals_by_id[inspector.eval_id]
        ?.declared_splits ?? []}
      on:close={() => (inspector = null)}
    />
  {/key}
{/if}
