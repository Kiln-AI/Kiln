<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount, tick } from "svelte"
  import type {
    AxisChange,
    EvoEdge,
    EvoForest,
  } from "$lib/utils/evolution/graph_assembly"
  import { AXIS_LABELS } from "$lib/utils/evolution/graph_assembly"
  import type { EvolutionLayout } from "$lib/utils/evolution/layout"
  import { NODE_H, NODE_W } from "$lib/utils/evolution/layout"
  import {
    MAP_KINDS,
    MAP_KIND_LABELS,
    MAP_KIND_STYLES,
    MAP_SIZES,
    layout_map,
    map_kinds,
    map_summary,
  } from "$lib/utils/evolution/map_view"
  import type { NodeDisplay } from "$lib/utils/evolution/score_lens"
  import { diff_tool_axis } from "$lib/utils/evolution/tool_diff"
  import {
    available_tools,
    model_info,
    model_name,
    prompt_name_from_id,
    provider_name_from_id,
  } from "$lib/stores"
  import type { PromptResponse } from "$lib/types"
  import Float from "$lib/ui/float.svelte"
  import EvolutionNode from "./evolution_node.svelte"

  export let forest: EvoForest
  export let layout: EvolutionLayout
  export let displays: Record<string, NodeDisplay> = {}
  export let selected_id: string | null = null
  export let project_id: string
  export let prompts: PromptResponse | null = null
  export let pins: string[] = []
  // "map" draws every run config as a small block (lineage tree plus the
  // unlinked ones); "detail" draws the full cards. The page owns the choice.
  export let view: "map" | "detail" = "detail"
  // The page's graph card fills the window (the page owns that state)
  export let expanded = false
  // Simple mode (the page's default): map only, and a click on a block adds it
  // to the page's charts or takes it out, instead of opening its card.
  export let simple = false
  // Chart color of each run config in the charts, for the ring on its block
  export let pin_colors: Record<string, string> = {}

  const dispatch = createEventDispatcher<{
    select: string | null
    toggle_pin: string
    view_change: "map" | "detail"
    toggle_expand: void
  }>()

  // Max name badges shown per direction on the tools axis tooltip
  const MAX_TOOL_BADGES = 4

  function scalar_axis_value(change: AxisChange, value: string): string {
    if (value === "") {
      return "—"
    }
    switch (change.axis) {
      case "model":
        return model_name(value, $model_info)
      case "provider":
        return provider_name_from_id(value)
      case "prompt":
        return prompt_name_from_id(value, prompts)
      default:
        return value
    }
  }

  const MIN_ZOOM = 0.25
  const MAX_ZOOM = 2
  // Zoom a map block opens its card at in the detail view
  const FOCUS_ZOOM = 1

  $: map_layout = layout_map(forest)
  $: kinds = map_kinds(forest)
  $: summary = map_summary(forest, kinds)
  $: active_layout = view === "map" ? map_layout : layout

  let viewport_el: HTMLDivElement | null = null
  let tx = 0
  let ty = 0
  let k = 1

  let panning = false
  let pan_moved = false
  let pan_start = { x: 0, y: 0, tx: 0, ty: 0 }

  let hovered_edge_id: string | null = null
  let hovered_map_id: string | null = null
  // Viewport size the current transform was set for (see handle_resize)
  let last_size: { w: number; h: number } | null = null

  // The lowest zoom is the fit zoom when the whole world needs less than
  // MIN_ZOOM, so Fit (and zooming out) always reaches the whole graph.
  let zoom_floor = MIN_ZOOM

  function clamp_zoom(value: number): number {
    return Math.min(MAX_ZOOM, Math.max(zoom_floor, value))
  }

  export function fit() {
    if (!viewport_el) {
      return
    }
    const { width, height } = active_layout.world
    const vw = viewport_el.clientWidth
    const vh = viewport_el.clientHeight
    // This transform is for the current size: a resize the observer has not
    // reported yet must not shift it again.
    last_size = { w: vw, h: vh }
    if (width <= 0 || height <= 0 || vw <= 0 || vh <= 0) {
      tx = 40
      ty = 40
      k = 1
      return
    }
    // Fit the world bbox with a 40px margin on each side. A deep (tall) graph
    // can bottom out at MIN_ZOOM and still not fit, in which case the view is
    // anchored at the top-left corner of the world rather than centered on its
    // middle - the roots are where you start reading.
    const fit_k = Math.min((vw - 80) / width, (vh - 80) / height)
    zoom_floor = Math.min(MIN_ZOOM, fit_k)
    k = clamp_zoom(fit_k)
    tx = width * k + 80 <= vw ? (vw - width * k) / 2 : 40
    ty = height * k + 80 <= vh ? (vh - height * k) / 2 : 40
  }

  export function zoom_by(factor: number) {
    if (!viewport_el) {
      return
    }
    zoom_at(
      viewport_el.clientWidth / 2,
      viewport_el.clientHeight / 2,
      clamp_zoom(k * factor),
    )
  }

  // Zoom keeping the viewport point (cx, cy) fixed on the same world point
  function zoom_at(cx: number, cy: number, new_k: number) {
    const world_x = (cx - tx) / k
    const world_y = (cy - ty) / k
    k = new_k
    tx = cx - world_x * k
    ty = cy - world_y * k
  }

  function handle_wheel(event: WheelEvent) {
    if (!viewport_el) {
      return
    }
    const rect = viewport_el.getBoundingClientRect()
    zoom_at(
      event.clientX - rect.left,
      event.clientY - rect.top,
      clamp_zoom(k * Math.exp(-event.deltaY / 400)),
    )
  }

  function is_background_event(event: Event): boolean {
    const target = event.target as HTMLElement | null
    return !target?.closest("[data-evolution-node]")
  }

  function handle_pointer_down(event: PointerEvent) {
    if (!is_background_event(event)) {
      return
    }
    panning = true
    pan_moved = false
    pan_start = { x: event.clientX, y: event.clientY, tx, ty }
    viewport_el?.setPointerCapture(event.pointerId)
  }

  function handle_pointer_move(event: PointerEvent) {
    if (!panning) {
      return
    }
    const dx = event.clientX - pan_start.x
    const dy = event.clientY - pan_start.y
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      pan_moved = true
    }
    tx = pan_start.tx + dx
    ty = pan_start.ty + dy
  }

  function handle_pointer_up(event: PointerEvent) {
    if (!panning) {
      return
    }
    panning = false
    if (viewport_el?.hasPointerCapture(event.pointerId)) {
      viewport_el.releasePointerCapture(event.pointerId)
    }
    // A stationary press-release on the background deselects
    if (!pan_moved) {
      dispatch("select", null)
    }
  }

  function handle_dblclick(event: MouseEvent) {
    if (is_background_event(event)) {
      fit()
    }
  }

  // Center the viewport on one node of the detail layout
  function focus_node(id: string) {
    const pos = layout.positions.get(id)
    if (!viewport_el || !pos) {
      return
    }
    const vw = viewport_el.clientWidth
    const vh = viewport_el.clientHeight
    last_size = { w: vw, h: vh }
    k = clamp_zoom(FOCUS_ZOOM)
    tx = vw / 2 - (pos.x + NODE_W / 2) * k
    ty = vh / 2 - (pos.y + NODE_H / 2) * k
  }

  // A map block opens its card in the detail view. A run config with no parent
  // has no card there, so it is only selected (its detail panel docks).
  let pending_focus_id: string | null = null
  function click_map_node(id: string) {
    if (simple) {
      dispatch("toggle_pin", id)
    } else {
      open_from_map(id)
    }
  }
  function open_from_map(id: string) {
    dispatch("select", id)
    if (!layout.positions.has(id)) {
      return
    }
    pending_focus_id = id
    dispatch("view_change", "detail")
  }

  let last_view = view
  $: handle_view_change(view)
  async function handle_view_change(new_view: "map" | "detail") {
    if (new_view === last_view) {
      return
    }
    last_view = new_view
    hovered_map_id = null
    await tick()
    if (pending_focus_id) {
      focus_node(pending_focus_id)
      pending_focus_id = null
    } else {
      fit()
    }
  }

  // Keep the world point at the viewport center fixed when the viewport
  // changes size (the detail panel docking, a window resize). Expanding or
  // shrinking the card re-fits instead: the reader wants the whole graph.
  let fit_on_next_resize = false
  function handle_resize() {
    if (!viewport_el) {
      return
    }
    const w = viewport_el.clientWidth
    const h = viewport_el.clientHeight
    if (last_size && (w !== last_size.w || h !== last_size.h)) {
      if (fit_on_next_resize) {
        fit_on_next_resize = false
        fit()
      } else {
        tx += (w - last_size.w) / 2
        ty += (h - last_size.h) / 2
      }
    }
    last_size = { w, h }
  }

  let last_expanded = expanded
  $: if (expanded !== last_expanded) {
    last_expanded = expanded
    fit_on_next_resize = true
  }

  let resize_observer: ResizeObserver | null = null
  onMount(() => {
    fit()
    resize_observer = new ResizeObserver(handle_resize)
    if (viewport_el) {
      resize_observer.observe(viewport_el)
    }
  })
  onDestroy(() => {
    resize_observer?.disconnect()
  })

  // Data arrives async after mount; run the initial fit once the world has a
  // real size (and the viewport has been measured).
  let did_initial_fit = false
  $: if (!did_initial_fit && viewport_el && active_layout.world.width > 0) {
    did_initial_fit = true
    fit()
  }

  $: map_nodes = [...forest.nodes.values()].filter((n) =>
    map_layout.positions.has(n.id),
  )
  $: hovered_map_node = hovered_map_id
    ? forest.nodes.get(hovered_map_id) ?? null
    : null
  $: hovered_map_pos = hovered_map_id
    ? map_layout.positions.get(hovered_map_id) ?? null
    : null

  $: positioned_nodes = [...forest.nodes.values()].filter((n) =>
    layout.positions.has(n.id),
  )

  function edge_stroke(edge: EvoEdge, hovered_id: string | null): string {
    return hovered_id === edge.id ? "#415CF5" : "#d1d5db"
  }
</script>

<!-- Fills whatever box the page gives it: the graph section is a card that may
     also hold the docked detail panel, so the card owns the height and border
     and this viewport takes the width that's left. -->
<div class="h-full w-full flex flex-col">
  <!-- Header: what the graph holds, the map legend and the view controls. The
       controls live here, not in the page toolbar, so they stay in reach when
       the card is full screen. -->
  <div
    class="flex-none flex flex-col gap-2 px-3 py-2 border-b border-gray-200 bg-white"
  >
    <div class="flex flex-row flex-wrap items-center gap-x-4 gap-y-2">
      <div class="flex flex-row items-baseline gap-2 whitespace-nowrap">
        <span class="text-sm font-medium text-gray-900">
          {summary.runConfigs} run configs
        </span>
        <span class="text-xs text-gray-500">
          {summary.models} models · {summary.providers} providers
        </span>
      </div>
      <div class="flex-grow"></div>
      {#if !simple}
        <div class="join" role="group" aria-label="Graph view">
          <button
            type="button"
            class="join-item btn btn-sm font-normal {view === 'map'
              ? 'btn-active'
              : ''}"
            aria-pressed={view === "map"}
            title="Every run config as a small block"
            on:click={() => dispatch("view_change", "map")}
          >
            Map
          </button>
          <button
            type="button"
            class="join-item btn btn-sm font-normal {view === 'detail'
              ? 'btn-active'
              : ''}"
            aria-pressed={view === "detail"}
            title="The lineage as full cards"
            on:click={() => dispatch("view_change", "detail")}
          >
            Cards
          </button>
        </div>
      {/if}
      <div class="join">
        <button
          class="btn btn-sm btn-outline join-item"
          title="Zoom out"
          on:click={() => zoom_by(1 / 1.25)}
        >
          −
        </button>
        <button
          class="btn btn-sm btn-outline join-item"
          title="Fit graph to view"
          on:click={() => fit()}
        >
          Fit
        </button>
        <button
          class="btn btn-sm btn-outline join-item"
          title="Zoom in"
          on:click={() => zoom_by(1.25)}
        >
          +
        </button>
      </div>
      <button
        type="button"
        class="btn btn-sm btn-outline font-normal"
        title={expanded ? "Back to the page (Esc)" : "Fill the window"}
        on:click={() => dispatch("toggle_expand")}
      >
        {expanded ? "Close" : "Expand"}
      </button>
    </div>
    {#if view === "map"}
      <div
        class="flex flex-row flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-600"
      >
        {#each MAP_KINDS as kind}
          {@const count = summary.kindCounts.get(kind) ?? 0}
          {#if count > 0}
            <span class="flex flex-row items-center gap-1.5 whitespace-nowrap">
              <span
                class="w-3 h-3 rounded-sm flex-none border {MAP_KIND_STYLES[
                  kind
                ].dashed
                  ? 'border-dashed'
                  : ''}"
                style="background-color: {MAP_KIND_STYLES[kind]
                  .fill}; border-color: {MAP_KIND_STYLES[kind].stroke};"
              ></span>
              {MAP_KIND_LABELS[kind]}
              <span class="text-gray-400">{count}</span>
            </span>
          {/if}
        {/each}
      </div>
    {/if}
  </div>

  <div
    bind:this={viewport_el}
    class="relative flex-1 min-h-0 overflow-hidden w-full bg-gray-50 select-none touch-none {panning
      ? 'cursor-grabbing'
      : 'cursor-grab'}"
    role="application"
    aria-label="Run config lineage graph. Drag to pan, scroll to zoom, double-click to fit."
    on:pointerdown={handle_pointer_down}
    on:pointermove={handle_pointer_move}
    on:pointerup={handle_pointer_up}
    on:pointercancel={handle_pointer_up}
    on:wheel|preventDefault={handle_wheel}
    on:dblclick={handle_dblclick}
  >
    {#if view === "map"}
      <div
        class="absolute top-0 left-0"
        style="transform: translate({tx}px, {ty}px) scale({k}); transform-origin: 0 0;"
      >
        <svg
          class="absolute top-0 left-0 overflow-visible"
          width={Math.max(map_layout.world.width, 1)}
          height={Math.max(map_layout.world.height, 1)}
        >
          {#each forest.edges as edge (edge.id)}
            {@const path = map_layout.edgePaths.get(edge.id)}
            {#if path}
              <path
                d={path.d}
                fill="none"
                stroke="#9ca3af"
                stroke-width="1.25"
                vector-effect="non-scaling-stroke"
                stroke-dasharray={edge.primary && !edge.cycleBroken
                  ? undefined
                  : "4 3"}
              />
            {/if}
          {/each}
          {#each map_nodes as node (node.id)}
            {@const pos = map_layout.positions.get(node.id) ?? { x: 0, y: 0 }}
            {@const style = MAP_KIND_STYLES[kinds.get(node.id) ?? "same"]}
            {#if pins.includes(node.id)}
              <!-- In the charts: a ring in the config's chart color -->
              <rect
                x={pos.x - 10}
                y={pos.y - 10}
                width={MAP_SIZES.nodeW + 20}
                height={MAP_SIZES.nodeH + 20}
                rx="12"
                fill="none"
                stroke={pin_colors[node.id] ?? "#415CF5"}
                stroke-width="4"
                vector-effect="non-scaling-stroke"
              />
            {/if}
            <rect
              data-evolution-node
              x={pos.x}
              y={pos.y}
              width={MAP_SIZES.nodeW}
              height={MAP_SIZES.nodeH}
              rx="6"
              fill={style.fill}
              stroke={selected_id === node.id ? "#415CF5" : style.stroke}
              stroke-width={selected_id === node.id ? 5 : 2}
              stroke-dasharray={style.dashed ? "4 3" : undefined}
              opacity={displays[node.id]?.dimmed ? 0.3 : 1}
              class="cursor-pointer"
              role="button"
              tabindex="0"
              aria-label={node.name}
              on:click={() => click_map_node(node.id)}
              on:keydown={(event) => {
                if (event.key === "Enter") {
                  click_map_node(node.id)
                }
              }}
              on:mouseenter={() => (hovered_map_id = node.id)}
              on:mouseleave={() => (hovered_map_id = null)}
            />
          {/each}
        </svg>
      </div>

      <!-- Labels and the hover card sit in screen space, so they keep their size
         at every zoom. -->
      {#if map_layout.unlinkedLabelAt}
        <div
          class="absolute text-xs text-gray-500 pointer-events-none whitespace-nowrap"
          style="left: {tx + map_layout.unlinkedLabelAt.x * k}px; top: {ty +
            map_layout.unlinkedLabelAt.y * k -
            20}px;"
        >
          {MAP_KIND_LABELS.unlinked} ({summary.kindCounts.get("unlinked") ?? 0})
        </div>
      {/if}
      {#if hovered_map_node && hovered_map_pos}
        <div
          class="absolute max-w-[340px] bg-white border border-gray-200 rounded-lg shadow-md px-3 py-2 text-xs pointer-events-none"
          style="left: {tx +
            (hovered_map_pos.x + MAP_SIZES.nodeW) * k +
            8}px; top: {ty + hovered_map_pos.y * k}px;"
        >
          <div class="font-medium text-gray-900">{hovered_map_node.name}</div>
          {#if displays[hovered_map_node.id]?.subtitle}
            <div class="text-gray-500 truncate">
              {displays[hovered_map_node.id].subtitle}
            </div>
          {/if}
          <div class="text-gray-500 mt-1">
            {MAP_KIND_LABELS[kinds.get(hovered_map_node.id) ?? "same"]}
          </div>
          {#if hovered_map_node.noteSummary}
            <div
              class="text-gray-500 italic mt-1 border-t border-gray-100 pt-1"
            >
              {hovered_map_node.noteSummary}
            </div>
          {/if}
          {#if simple && !hovered_map_node.ghost}
            <div class="text-gray-400 mt-1">
              {pins.includes(hovered_map_node.id)
                ? "In the charts below. Click to take it out."
                : "Click to add it to the charts below."}
            </div>
          {/if}
        </div>
      {/if}
    {:else}
      <div
        class="absolute top-0 left-0"
        style="transform: translate({tx}px, {ty}px) scale({k}); transform-origin: 0 0;"
      >
        <!-- Edge underlay -->
        <svg
          class="absolute top-0 left-0 overflow-visible pointer-events-none"
          width={Math.max(layout.world.width, 1)}
          height={Math.max(layout.world.height, 1)}
          aria-hidden="true"
        >
          {#each forest.edges as edge (edge.id)}
            {@const path = layout.edgePaths.get(edge.id)}
            {#if path}
              <path
                d={path.d}
                fill="none"
                stroke={edge_stroke(edge, hovered_edge_id)}
                stroke-width="1.5"
                stroke-dasharray={edge.primary && !edge.cycleBroken
                  ? undefined
                  : "5 4"}
              />
              <!-- Wide transparent hit stroke for hover -->
              <path
                d={path.d}
                fill="none"
                stroke="transparent"
                stroke-width="12"
                class="pointer-events-auto"
                role="presentation"
                on:mouseenter={() => (hovered_edge_id = edge.id)}
                on:mouseleave={() => (hovered_edge_id = null)}
              />
            {/if}
          {/each}
        </svg>

        <!-- Midpoint chips: up to 2 changed-axis names + overflow count. Each chip
         container doubles as the Floating UI anchor for the hover card. -->
        {#each forest.edges as edge (edge.id + "-chip")}
          {@const path = layout.edgePaths.get(edge.id)}
          {#if path}
            <div
              class="absolute flex flex-row gap-0.5 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
              style="left: {path.chipAt.x}px; top: {path.chipAt.y}px;"
            >
              {#each edge.changedAxes.slice(0, 2) as change}
                <span
                  class="badge badge-xs bg-white border-gray-300 text-gray-600 text-[9px] whitespace-nowrap"
                >
                  {AXIS_LABELS[change.axis]}
                </span>
              {/each}
              {#if edge.changedAxes.length > 2}
                <span
                  class="badge badge-xs bg-white border-gray-300 text-gray-600 text-[9px] whitespace-nowrap"
                >
                  +{edge.changedAxes.length - 2}
                </span>
              {/if}
              {#if hovered_edge_id === edge.id}
                <Float
                  placement="bottom"
                  offset_px={10}
                  portal={true}
                  role="none"
                >
                  <div
                    class="max-w-[340px] bg-white border border-gray-200 rounded-lg shadow-md px-3 py-2 text-xs pointer-events-none"
                  >
                    {#if edge.cycleBroken}
                      <div class="text-error font-medium mb-1">
                        Cycle detected — this link was ignored for layout
                      </div>
                    {/if}
                    {#if edge.changedAxes.length > 0}
                      <div class="space-y-1.5">
                        {#each edge.changedAxes as change}
                          {#if change.axis === "tools"}
                            {@const tool_diff = diff_tool_axis(
                              change.from,
                              change.to,
                              $available_tools[project_id],
                            )}
                            <div>
                              {#if tool_diff.tools_added.length > 0 || tool_diff.tools_removed.length > 0}
                                <div class="text-gray-700">
                                  <span class="font-medium">Tools:</span>
                                  +{tool_diff.tools_added.length} / −{tool_diff
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
                                  <span class="font-medium">Skills:</span>
                                  +{tool_diff.skills_added.length}/−{tool_diff
                                    .skills_removed.length}
                                </div>
                              {/if}
                            </div>
                          {:else}
                            <div class="text-gray-700">
                              <span class="font-medium">
                                {AXIS_LABELS[change.axis]}:
                              </span>
                              {scalar_axis_value(change, change.from)} → {scalar_axis_value(
                                change,
                                change.to,
                              )}
                            </div>
                          {/if}
                        {/each}
                      </div>
                    {:else}
                      <div class="text-gray-500">No axis changes recorded</div>
                    {/if}
                    {#if edge.noteSummary}
                      <div
                        class="text-gray-500 italic mt-1 border-t border-gray-100 pt-1"
                      >
                        {edge.noteSummary}
                      </div>
                    {/if}
                  </div>
                </Float>
              {/if}
            </div>
          {/if}
        {/each}

        <!-- Node cards -->
        {#each positioned_nodes as node (node.id)}
          {@const pos = layout.positions.get(node.id) ?? { x: 0, y: 0 }}
          <div
            class="absolute"
            style="left: {pos.x}px; top: {pos.y}px;"
            data-evolution-node
          >
            <EvolutionNode
              {node}
              display={displays[node.id]}
              selected={selected_id === node.id}
              pinned={pins.includes(node.id)}
              on:select={(event) => dispatch("select", event.detail)}
              on:toggle_pin={(event) => dispatch("toggle_pin", event.detail)}
            />
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
