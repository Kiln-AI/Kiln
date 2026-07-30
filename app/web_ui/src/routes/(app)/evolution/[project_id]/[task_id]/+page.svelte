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
    score_key_label,
    strip_cells,
  } from "$lib/utils/evolution/score_lens"
  import type { PromptResponse, ProviderModels } from "$lib/types"
  import { fly } from "svelte/transition"
  import { cubicOut } from "svelte/easing"
  import CompareRadarChart from "$lib/components/compare_radar_chart.svelte"
  import EvolutionCanvas from "./evolution_canvas.svelte"
  import NodeDetailPanel from "./node_detail_panel.svelte"
  import UnlinkedSection from "./unlinked_section.svelte"
  import CompareMatrix from "./compare_matrix.svelte"
  import EvalInspector from "./eval_inspector.svelte"
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
  }

  // After data loads, drop URL state that doesn't resolve against it
  function validateStateFromURL() {
    if (selected_id && !forest.nodes.has(selected_id)) {
      selected_id = null
    }
    pins = pins.filter((id) => forest.nodes.has(id)).slice(0, MAX_PINS)
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

    // Replace state: this only records existing UI state in the URL.
    // noScroll/keepFocus so selecting a node doesn't jump the page.
    const query = urlParams.toString()
    const newURL = `${$page.url.pathname}${query ? `?${query}` : ""}`
    goto(newURL, { replaceState: true, noScroll: true, keepFocus: true })
  }

  // Reactive statement to sync state to the URL when it changes
  $: if (
    !isInitializing &&
    (lens_selected ||
      selected_id ||
      starred_only ||
      unlinked_expanded ||
      pins ||
      true)
  ) {
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

  // ---- Radar chart inputs -------------------------------------------------
  // The radar takes the same shape the old compare page feeds it; here it is
  // derived from the lens data instead of that page's comparison table.

  // Same shape the radar chart declares internally (it isn't exported)
  type ComparisonFeature = {
    category: string
    items: { label: string; key: string }[]
    has_default_eval_config: boolean | undefined
    eval_id: string
  }

  $: comparison_features = build_features(lens_data.keyMetas)
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
    for (const meta of lens_data.keyMetas) {
      const key = score_key_id(meta.evalId, meta.scoreKey)
      switch (meta.type) {
        case "five_star":
          maxes[key] = 5
          break
        case "pass_fail":
        case "pass_fail_critical":
          maxes[key] = 1
          break
      }
    }
    return maxes
  })()

  $: score_directions = (() => {
    const directions: Record<string, string> = {}
    for (const meta of lens_data.keyMetas) {
      directions[score_key_id(meta.evalId, meta.scoreKey)] = meta.direction
    }
    return directions
  })()

  // The radar drops lower-is-better and informational scores (a radar reads
  // "further from center is better"), so count what's left to know whether it
  // will draw anything at all.
  $: radar_axis_count = lens_data.keyMetas.filter(
    (meta) =>
      meta.direction !== "lower_is_better" &&
      meta.direction !== "informational",
  ).length
  $: radar_available =
    pinned_nodes.length > 0 && radar_axis_count >= MIN_RADAR_AXES

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

    <!-- Row 1: the lineage graph (tall, its own pan/zoom) beside the radar -->
    <div class="grid gap-4 grid-cols-1 lg:grid-cols-[minmax(400px,2fr)_3fr]">
      <div class="min-w-0">
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
          <!-- Empty state: no lineage recorded at all -->
          <div
            class="h-[calc(100vh-240px)] min-h-[560px] bg-gray-50 border border-gray-200 rounded-lg px-6 flex flex-col justify-center items-center text-center"
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
      <div class="min-w-0 min-h-[560px] flex flex-col">
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
            onConfigClick={(id) => handle_select(id)}
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
    </div>

    <!-- Row 2: the comparison matrix, full page width -->
    {#if pinned_nodes.length > 0}
      <div class="mt-6">
        <div class="text-sm font-medium text-gray-900 mb-2">
          Comparison ({pinned_nodes.length}
          {pinned_nodes.length === 1 ? "config" : "configs"})
        </div>
        <CompareMatrix
          {pinned_nodes}
          {lens_data}
          {eval_scores_cache}
          {eval_scores_loading}
          on:select={(event) => handle_select(event.detail)}
          on:inspect={(event) =>
            open_inspector(event.detail.eval_id, event.detail.run_config_id)}
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

<!-- Detail panel and artifact pane are fixed right-side drawers, so selecting
     a node never reflows the canvas. The artifact pane stacks to the left of
     the detail panel when both are open. -->
{#if !loading && !load_error && selected_node}
  <div
    class="fixed top-16 right-0 bottom-0 w-[440px] bg-white border-l border-gray-200 shadow-xl z-30 overflow-hidden"
    transition:fly={{ x: 440, duration: 180, easing: cubicOut }}
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
        selected_node && open_inspector(event.detail.eval_id, selected_node.id)}
    />
  </div>
{/if}

{#if !loading && !load_error && pane_target}
  <div
    class="fixed top-16 bottom-0 w-[440px] bg-white border-l border-gray-200 shadow-xl z-30 overflow-hidden transition-[right] duration-200 ease-out"
    style="right: {selected_node ? 440 : 0}px;"
    transition:fly={{ x: 440, duration: 180, easing: cubicOut }}
  >
    <ArtifactPane
      target={pane_target}
      {project_id}
      {task_id}
      {prompts}
      on:close={() => (pane_target = null)}
    />
  </div>
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
