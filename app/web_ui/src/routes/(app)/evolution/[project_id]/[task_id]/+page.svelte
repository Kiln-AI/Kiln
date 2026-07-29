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
  import type { EvoNode } from "$lib/utils/evolution/graph_assembly"
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
    strip_cell_color,
    strip_cells,
  } from "$lib/utils/evolution/score_lens"
  import type { PromptResponse, ProviderModels } from "$lib/types"
  import EvolutionCanvas from "./evolution_canvas.svelte"
  import NodeDetailPanel from "./node_detail_panel.svelte"
  import UnlinkedSection from "./unlinked_section.svelte"

  type EvalResultsSummaryResponse =
    components["schemas"]["EvalResultsSummaryResponse"]
  type RunConfigEvalScoresSummary =
    components["schemas"]["RunConfigEvalScoresSummary"]

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  agentInfo.set({
    name: "Evolution",
    description: "Run config lineage graph with eval results",
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
    starred_only = urlParams.get("starred") === "1"
    unlinked_expanded = urlParams.get("unlinked") === "1"
  }

  // After data loads, drop URL state that doesn't resolve against it
  function validateStateFromURL() {
    if (selected_id && !forest.nodes.has(selected_id)) {
      selected_id = null
    }
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
    (lens_selected || selected_id || starred_only || unlinked_expanded || true)
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
        strip_colors: cells.map((cell) => strip_cell_color(cell.sign)),
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
  title="Evolution"
  subtitle="Lineage of your run configs and how each change scored"
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

    {#if forest.edges.length === 0}
      <!-- Empty state: no lineage recorded at all -->
      <div
        class="bg-gray-50 border border-gray-200 rounded-lg px-6 py-8 text-center"
      >
        <div class="text-lg font-medium text-gray-900 mb-1">
          No lineage recorded yet
        </div>
        <div class="text-sm text-gray-500 max-w-lg mx-auto">
          None of this task's run configs declare a parent. When a run config is
          derived from another, the link appears here as a lineage graph.
        </div>
      </div>
      <div class="flex flex-row gap-4 items-start">
        <div class="flex-1 min-w-0">
          <UnlinkedSection
            nodes={unlinked_nodes}
            {displays}
            {selected_id}
            expanded={true}
            collapsible={false}
            on:select={(event) => handle_select(event.detail)}
          />
        </div>
        {#if selected_node}
          <div class="w-[420px] flex-none mt-8">
            <NodeDetailPanel
              node={selected_node}
              {forest}
              {project_id}
              {task_id}
              {lens_data}
              eval_scores={eval_scores_cache[selected_node.id] ?? null}
              eval_scores_loading={eval_scores_loading[selected_node.id] ??
                false}
              eval_scores_error={eval_scores_errors[selected_node.id] ?? null}
              on:close={() => handle_select(null)}
              on:select={(event) => handle_select(event.detail)}
            />
          </div>
        {/if}
      </div>
    {:else}
      <div
        class="grid gap-4"
        style="grid-template-columns: {selected_node
          ? 'minmax(0, 1fr) 420px'
          : 'minmax(0, 1fr)'};"
      >
        <EvolutionCanvas
          bind:this={canvas}
          {forest}
          {layout}
          {displays}
          {selected_id}
          on:select={(event) => handle_select(event.detail)}
        />
        {#if selected_node}
          <NodeDetailPanel
            node={selected_node}
            {forest}
            {project_id}
            {task_id}
            {lens_data}
            eval_scores={eval_scores_cache[selected_node.id] ?? null}
            eval_scores_loading={eval_scores_loading[selected_node.id] ?? false}
            eval_scores_error={eval_scores_errors[selected_node.id] ?? null}
            on:close={() => handle_select(null)}
            on:select={(event) => handle_select(event.detail)}
          />
        {/if}
      </div>

      <UnlinkedSection
        nodes={unlinked_nodes}
        {displays}
        {selected_id}
        expanded={unlinked_expanded}
        on:toggle={() => (unlinked_expanded = !unlinked_expanded)}
        on:select={(event) => handle_select(event.detail)}
      />
    {/if}
  {/if}
</AppPage>
