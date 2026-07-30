<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { components } from "$lib/api_schema"
  import type {
    EvoForest,
    EvoNode,
    AxisKey,
  } from "$lib/utils/evolution/graph_assembly"
  import {
    AXIS_KEYS,
    AXIS_LABELS,
    get_axis_values,
    primary_parent_id,
  } from "$lib/utils/evolution/graph_assembly"
  import type { LensData } from "$lib/utils/evolution/score_lens"
  import {
    lens_color,
    normalized_score,
    percent_complete,
    raw_score,
  } from "$lib/utils/evolution/score_lens"
  import {
    available_tools,
    get_task_composite_id,
    model_info,
    model_name,
    prompt_name_from_id,
    provider_name_from_id,
  } from "$lib/stores"
  import { prompts_by_task_composite_id } from "$lib/stores/prompts_store"
  import { isKilnAgentRunConfig } from "$lib/types"
  import {
    formatDate,
    formatLatency,
    score_key_label,
  } from "$lib/utils/formatters"
  import { getRunConfigUiProperties } from "$lib/utils/run_config_formatters"
  import { diff_tool_axis } from "$lib/utils/evolution/tool_diff"
  import PropertyList from "$lib/ui/property_list.svelte"
  import StarIcon from "$lib/ui/icons/star_icon.svelte"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import ChevronRightIcon from "$lib/ui/icons/chevron_right_icon.svelte"
  import type { ArtifactPaneTarget } from "./artifact_pane.svelte"

  type RunConfigEvalScoresSummary =
    components["schemas"]["RunConfigEvalScoresSummary"]

  export let node: EvoNode
  export let forest: EvoForest
  export let project_id: string
  export let task_id: string
  export let lens_data: LensData
  export let eval_scores: RunConfigEvalScoresSummary | null = null
  export let eval_scores_loading: boolean = false
  export let eval_scores_error: string | null = null
  export let pinned: boolean = false

  const dispatch = createEventDispatcher<{
    close: undefined
    select: string
    toggle_pin: string
    open_pane: ArtifactPaneTarget
    inspect: { eval_id: string }
  }>()

  // Cap on +/− tool name badges shown per direction in the diff table
  const MAX_TOOL_BADGES = 4

  const DELTA_BETTER_COLOR = "#006300"
  const DELTA_WORSE_COLOR = "#d03b3b"

  let active_tab: "overview" | "diff" | "evals" = "overview"
  let show_unchanged = false

  // Reset the diff-parent selection when the selected node changes
  let diff_parent_id: string | null = null
  let last_node_id: string | null = null
  $: if (node.id !== last_node_id) {
    last_node_id = node.id
    diff_parent_id = primary_parent_id(node)
  }

  $: prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  $: agent_props =
    node.config && isKilnAgentRunConfig(node.config.run_config_properties)
      ? node.config.run_config_properties
      : null

  function open_prompt_pane() {
    if (!agent_props) {
      return
    }
    dispatch("open_pane", {
      kind: "prompt",
      title: "Prompt",
      prompt_ids: [agent_props.prompt_id],
    })
  }

  // "View both": parent prompt + this config's prompt stacked in the modal
  function open_prompt_diff_pane(from_prompt_id: string, to_prompt_id: string) {
    dispatch("open_pane", {
      kind: "prompt",
      title: "Prompt comparison",
      prompt_ids: [from_prompt_id, to_prompt_id],
    })
  }

  function open_run_config_pane() {
    if (!node.config) {
      return
    }
    dispatch("open_pane", {
      kind: "run_config",
      run_config: node.config,
    })
  }

  $: diff_parent = diff_parent_id
    ? forest.nodes.get(diff_parent_id) ?? null
    : null

  function node_name(id: string): string {
    return forest.nodes.get(id)?.name ?? id
  }

  function display_axis_value(axis: AxisKey, value: string): string {
    if (value === "") {
      return "—"
    }
    switch (axis) {
      case "model":
        return model_name(value, $model_info)
      case "provider":
        return provider_name_from_id(value)
      case "prompt":
        return prompt_name_from_id(value, prompts)
      case "tools": {
        const count = value.split(", ").filter((t) => t.length > 0).length
        return `${count} tool${count === 1 ? "" : "s"}`
      }
      default:
        return value
    }
  }

  interface DiffRow {
    axis: AxisKey
    from: string
    to: string
    changed: boolean
  }

  $: diff_rows = build_diff_rows(node, diff_parent)
  function build_diff_rows(
    child: EvoNode,
    parent: EvoNode | null,
  ): DiffRow[] | null {
    const child_values = get_axis_values(child.config)
    const parent_values = parent ? get_axis_values(parent.config) : null
    if (!child_values || !parent_values) {
      return null
    }
    return AXIS_KEYS.map((axis) => ({
      axis,
      from: parent_values[axis],
      to: child_values[axis],
      changed: parent_values[axis] !== child_values[axis],
    }))
  }
  $: changed_diff_rows = (diff_rows ?? []).filter((row) => row.changed)
  $: visible_diff_rows = show_unchanged ? diff_rows ?? [] : changed_diff_rows

  interface EvalRow {
    evalId: string
    evalName: string
    scoreKey: string
    label: string
    raw: number | null
    normalized: number | null
    delta: number | null
    informational: boolean
    n_used: number | null
    percent: number | null
  }

  $: eval_rows = build_eval_rows(lens_data, node, eval_scores)
  function build_eval_rows(
    data: LensData,
    for_node: EvoNode,
    scores: RunConfigEvalScoresSummary | null,
  ): EvalRow[] {
    const parent_id = primary_parent_id(for_node)
    const rows = data.keyMetas.map((meta) => {
      const raw = raw_score(data, for_node.id, meta.evalId, meta.scoreKey)
      const normalized = normalized_score(
        data,
        for_node.id,
        meta.evalId,
        meta.scoreKey,
      )
      let delta: number | null = null
      if (parent_id && meta.direction !== "informational") {
        const parent_normalized = normalized_score(
          data,
          parent_id,
          meta.evalId,
          meta.scoreKey,
        )
        if (normalized !== null && parent_normalized !== null) {
          delta = normalized - parent_normalized
        }
      }
      const score_summary = scores?.eval_results.find(
        (result) => result.eval_id === meta.evalId,
      )?.eval_config_result?.results[meta.scoreKey]
      return {
        evalId: meta.evalId,
        evalName: meta.evalName,
        scoreKey: meta.scoreKey,
        label: score_key_label(meta.scoreKey),
        raw,
        normalized,
        delta,
        informational: meta.direction === "informational",
        n_used: score_summary?.n_used ?? null,
        percent: percent_complete(data, for_node.id, meta.evalId),
      }
    })
    // Largest movement first; informational rows sink to the bottom
    rows.sort((a, b) => {
      if (a.informational !== b.informational) {
        return a.informational ? 1 : -1
      }
      const delta_a = a.delta === null ? -1 : Math.abs(a.delta)
      const delta_b = b.delta === null ? -1 : Math.abs(b.delta)
      return delta_b - delta_a || a.label.localeCompare(b.label)
    })
    return rows
  }
</script>

<!-- Sized by its container: the page docks this as the right-hand column of the
     graph card, so it is exactly as tall as that section and scrolls inside. -->
<div class="h-full w-full bg-white flex flex-col overflow-hidden">
  <!-- Header -->
  <div class="flex items-start gap-2 px-4 pt-4 pb-2 flex-none">
    <div class="min-w-0 flex-1">
      <div
        class="font-medium text-gray-900 truncate flex items-center gap-1"
        title={node.name}
      >
        {#if node.starred}
          <span class="w-3.5 h-3.5 text-amber-500 flex-none">
            <StarIcon filled={true} />
          </span>
        {/if}
        <span class="truncate">{node.name}</span>
      </div>
      {#if node.ghost}
        <div class="text-xs text-gray-500 italic">
          This run config was deleted — only its ID remains.
        </div>
      {/if}
    </div>
    {#if !node.ghost}
      <button
        type="button"
        class="btn btn-xs {pinned ? 'btn-primary' : 'btn-outline'} flex-none"
        title={pinned ? "Remove from compare set" : "Pin to compare"}
        on:click={() => dispatch("toggle_pin", node.id)}
      >
        {pinned ? "Pinned" : "Pin to compare"}
      </button>
    {/if}
    <button
      type="button"
      class="w-6 h-6 rounded-full flex items-center justify-center p-1.5 text-gray-500 hover:bg-gray-200 hover:text-gray-900 transition-colors flex-none"
      title="Close panel"
      on:click={() => dispatch("close")}
    >
      <CloseIcon />
    </button>
  </div>

  <!-- Tabs -->
  <div class="tabs tabs-boxed mx-4 mb-2 flex-none">
    <button
      class="tab {active_tab === 'overview' ? 'tab-active' : ''}"
      on:click={() => (active_tab = "overview")}
    >
      Overview
    </button>
    <button
      class="tab {active_tab === 'diff' ? 'tab-active' : ''}"
      on:click={() => (active_tab = "diff")}
    >
      Diff vs Parent
    </button>
    <button
      class="tab {active_tab === 'evals' ? 'tab-active' : ''}"
      on:click={() => (active_tab = "evals")}
    >
      Evals
    </button>
  </div>

  <div class="flex-1 overflow-y-auto px-4 pb-4">
    {#if active_tab === "overview"}
      {#if node.ghost}
        <div class="text-sm text-gray-500 py-2">
          No configuration details are available for a deleted run config. Its
          lineage links are preserved below.
        </div>
      {:else if node.config}
        <PropertyList
          properties={getRunConfigUiProperties(
            project_id,
            task_id,
            node.config,
            $model_info,
            prompts,
            $available_tools,
            undefined,
            agent_props ? open_prompt_pane : undefined,
          )}
        />
      {/if}

      {#if node.noteFull}
        <div class="mt-4">
          <div
            class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1"
          >
            Provenance Note
          </div>
          <div class="text-sm text-gray-700 whitespace-pre-wrap break-words">
            {node.noteFull}
          </div>
        </div>
      {/if}

      {#if node.parents.length > 0}
        <div class="mt-4">
          <div
            class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1"
          >
            Parents
          </div>
          <div class="flex flex-wrap gap-1.5">
            {#each node.parents as parent (parent.parentId)}
              <button
                type="button"
                class="badge badge-ghost hover:badge-neutral gap-1"
                on:click={() => dispatch("select", parent.parentId)}
              >
                {node_name(parent.parentId)}
                {#if parent.primary && node.parents.length > 1}
                  <span class="text-[9px] uppercase text-gray-500">
                    primary
                  </span>
                {/if}
              </button>
            {/each}
          </div>
        </div>
      {/if}

      {#if node.children.length > 0}
        <div class="mt-4">
          <div
            class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1"
          >
            Children
          </div>
          <div class="flex flex-wrap gap-1.5">
            {#each node.children as child_id (child_id)}
              <button
                type="button"
                class="badge badge-ghost hover:badge-neutral"
                on:click={() => dispatch("select", child_id)}
              >
                {node_name(child_id)}
              </button>
            {/each}
          </div>
        </div>
      {/if}

      {#if !node.ghost}
        <div class="mt-4 text-xs text-gray-500">
          {#if node.created_at}
            Created {formatDate(node.created_at)}
          {/if}
          {#if node.config?.created_by}
            by {node.config.created_by}
          {/if}
          {#if node.origin}
            · Origin: {node.origin}
          {/if}
        </div>

        <div class="mt-4 flex gap-2">
          <a
            class="btn btn-sm btn-outline"
            href={`/optimize/${project_id}/${task_id}/run_config/${node.id}`}
          >
            Open run config
          </a>
          <button
            type="button"
            class="btn btn-sm btn-outline"
            title="Preview this run config's properties"
            on:click={open_run_config_pane}
          >
            Preview
          </button>
        </div>
      {/if}
    {:else if active_tab === "diff"}
      {#if node.parents.length === 0}
        <div class="text-sm text-gray-500 py-2">No parent recorded</div>
      {:else}
        {#if node.parents.length > 1}
          <label class="flex items-center gap-2 text-xs text-gray-500 mb-2">
            Compare against
            <select
              class="select select-bordered select-xs"
              bind:value={diff_parent_id}
            >
              {#each node.parents as parent (parent.parentId)}
                <option value={parent.parentId}>
                  {node_name(parent.parentId)}{parent.primary
                    ? " (primary)"
                    : ""}
                </option>
              {/each}
            </select>
          </label>
        {/if}

        {#if diff_parent?.ghost}
          <div class="text-sm text-gray-500 py-2">
            The parent config was deleted — no diff available.
          </div>
        {:else if diff_rows === null}
          <div class="text-sm text-gray-500 py-2">
            These configs can't be diffed (non-model run config).
          </div>
        {:else}
          {#if changed_diff_rows.length === 0}
            <div class="text-sm text-gray-500 py-2">
              No axis changes vs this parent.
            </div>
          {/if}
          {#if visible_diff_rows.length > 0}
            <table class="table table-xs w-full">
              <thead>
                <tr>
                  <th class="w-24"></th>
                  <th class="text-gray-500 font-normal">Parent</th>
                  <th class="text-gray-500 font-normal">This config</th>
                </tr>
              </thead>
              <tbody>
                {#each visible_diff_rows as row (row.axis)}
                  <tr class={row.changed ? "bg-amber-50" : ""}>
                    <td class="text-gray-500">{AXIS_LABELS[row.axis]}</td>
                    {#if row.axis === "tools" && row.changed}
                      {@const tool_diff = diff_tool_axis(
                        row.from,
                        row.to,
                        $available_tools[project_id],
                      )}
                      <td colspan="2">
                        {#if tool_diff.tools_added.length > 0 || tool_diff.tools_removed.length > 0}
                          <div class="text-gray-700">
                            Tools: +{tool_diff.tools_added.length} / −{tool_diff
                              .tools_removed.length}
                          </div>
                          <div class="flex flex-wrap gap-1 mt-0.5">
                            {#each tool_diff.tools_added.slice(0, MAX_TOOL_BADGES) as name}
                              <span
                                class="badge badge-xs bg-green-50 border-green-200 text-green-700 whitespace-nowrap max-w-[140px] truncate"
                                title={name}
                              >
                                +{name}
                              </span>
                            {/each}
                            {#each tool_diff.tools_removed.slice(0, MAX_TOOL_BADGES) as name}
                              <span
                                class="badge badge-xs bg-red-50 border-red-200 text-red-700 whitespace-nowrap max-w-[140px] truncate"
                                title={name}
                              >
                                −{name}
                              </span>
                            {/each}
                            {#if tool_diff.tools_added.length > MAX_TOOL_BADGES || tool_diff.tools_removed.length > MAX_TOOL_BADGES}
                              <span class="text-gray-500">
                                +{tool_diff.tools_added.length +
                                  tool_diff.tools_removed.length -
                                  Math.min(
                                    tool_diff.tools_added.length,
                                    MAX_TOOL_BADGES,
                                  ) -
                                  Math.min(
                                    tool_diff.tools_removed.length,
                                    MAX_TOOL_BADGES,
                                  )} more
                              </span>
                            {/if}
                          </div>
                        {/if}
                        {#if tool_diff.skills_added.length > 0 || tool_diff.skills_removed.length > 0}
                          <div class="text-gray-700 mt-0.5">
                            Skills: +{tool_diff.skills_added.length}/−{tool_diff
                              .skills_removed.length}
                          </div>
                        {/if}
                      </td>
                    {:else if row.axis === "prompt" && row.changed}
                      <td class="break-all">
                        {display_axis_value(row.axis, row.from)}
                      </td>
                      <td class="break-all font-medium">
                        {display_axis_value(row.axis, row.to)}
                        <button
                          type="button"
                          class="link text-xs font-normal text-gray-500 whitespace-nowrap"
                          title="View both prompts"
                          on:click={() =>
                            open_prompt_diff_pane(row.from, row.to)}
                        >
                          view both
                        </button>
                      </td>
                    {:else}
                      <td class="break-all">
                        {display_axis_value(row.axis, row.from)}
                      </td>
                      <td class="break-all {row.changed ? 'font-medium' : ''}">
                        {display_axis_value(row.axis, row.to)}
                      </td>
                    {/if}
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
          <label
            class="flex items-center gap-2 text-xs text-gray-500 mt-3 cursor-pointer"
          >
            <input
              type="checkbox"
              class="toggle toggle-xs"
              bind:checked={show_unchanged}
            />
            Show unchanged
          </label>
        {/if}
      {/if}
    {:else if active_tab === "evals"}
      {#if node.ghost}
        <div class="text-sm text-gray-500 py-2">
          No eval results — this run config was deleted.
        </div>
      {:else if eval_rows.length === 0}
        <div class="text-sm text-gray-500 py-2">No eval results yet.</div>
      {:else}
        <table class="table table-xs w-full">
          <thead>
            <tr>
              <th class="text-gray-500 font-normal">Score</th>
              <th class="text-gray-500 font-normal">Value</th>
              <th class="text-gray-500 font-normal">Δ vs parent</th>
              <th class="text-gray-500 font-normal text-right">n</th>
              <th class="text-gray-500 font-normal">Done</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each eval_rows as row (row.evalId + "::" + row.scoreKey)}
              <tr>
                <td>
                  <div class="font-medium text-gray-900">{row.label}</div>
                  <div class="text-[10px] text-gray-500">
                    {row.evalName}{row.informational ? " · informational" : ""}
                  </div>
                </td>
                <td>
                  <div class="flex items-center gap-1.5">
                    <span
                      class="w-2.5 h-2.5 rounded-full flex-none"
                      style="background-color: {lens_color(row.normalized)}"
                    ></span>
                    <span>{row.raw === null ? "—" : row.raw.toFixed(2)}</span>
                  </div>
                </td>
                <td>
                  {#if row.delta === null || row.informational}
                    <span class="text-gray-400">—</span>
                  {:else if row.delta > 0}
                    <span style="color: {DELTA_BETTER_COLOR}">
                      ▲ {row.delta.toFixed(2)}
                    </span>
                  {:else if row.delta < 0}
                    <span style="color: {DELTA_WORSE_COLOR}">
                      ▼ {Math.abs(row.delta).toFixed(2)}
                    </span>
                  {:else}
                    <span class="text-gray-500">0.00</span>
                  {/if}
                </td>
                <td class="text-right">
                  {#if row.n_used !== null}
                    {row.n_used}
                  {:else if eval_scores_loading}
                    <span class="loading loading-spinner loading-xs"></span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td>
                  <progress
                    class="progress progress-primary w-10"
                    value={row.percent ?? 0}
                    max="1"
                  ></progress>
                </td>
                <td class="text-right">
                  <button
                    type="button"
                    class="w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:text-gray-900 hover:bg-gray-100"
                    title="Inspect this eval's method and runs"
                    on:click={() =>
                      dispatch("inspect", { eval_id: row.evalId })}
                  >
                    <span class="w-3.5 h-3.5 block">
                      <ChevronRightIcon />
                    </span>
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>

        <!-- Usage footer from the lazy per-run-config eval scores -->
        <div class="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
          {#if eval_scores_loading}
            <span class="loading loading-spinner loading-xs"></span>
            Loading usage...
          {:else if eval_scores_error}
            <span class="text-error">{eval_scores_error}</span>
          {:else if eval_scores?.mean_usage}
            {@const usage = eval_scores.mean_usage}
            <div class="flex flex-wrap gap-x-4 gap-y-1">
              {#if usage.mean_cost !== null && usage.mean_cost !== undefined}
                <span>Mean cost: ${usage.mean_cost.toFixed(4)}</span>
              {/if}
              {#if usage.mean_total_tokens !== null && usage.mean_total_tokens !== undefined}
                <span>
                  Mean tokens: {Math.round(
                    usage.mean_total_tokens,
                  ).toLocaleString()}
                </span>
              {/if}
              {#if usage.mean_total_llm_latency_ms !== null && usage.mean_total_llm_latency_ms !== undefined}
                <span>
                  Mean latency: {formatLatency(usage.mean_total_llm_latency_ms)}
                </span>
              {/if}
            </div>
          {:else}
            No usage data recorded.
          {/if}
        </div>
      {/if}
    {/if}
  </div>
</div>
