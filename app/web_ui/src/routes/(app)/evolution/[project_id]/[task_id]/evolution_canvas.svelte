<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import type {
    AxisChange,
    EvoEdge,
    EvoForest,
  } from "$lib/utils/evolution/graph_assembly"
  import { AXIS_LABELS } from "$lib/utils/evolution/graph_assembly"
  import type { EvolutionLayout } from "$lib/utils/evolution/layout"
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

  const dispatch = createEventDispatcher<{
    select: string | null
    toggle_pin: string
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

  let viewport_el: HTMLDivElement | null = null
  let tx = 0
  let ty = 0
  let k = 1

  let panning = false
  let pan_moved = false
  let pan_start = { x: 0, y: 0, tx: 0, ty: 0 }

  let hovered_edge_id: string | null = null

  function clamp_zoom(value: number): number {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value))
  }

  export function fit() {
    if (!viewport_el) {
      return
    }
    const { width, height } = layout.world
    const vw = viewport_el.clientWidth
    const vh = viewport_el.clientHeight
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
    k = clamp_zoom(Math.min((vw - 80) / width, (vh - 80) / height))
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

  onMount(() => {
    fit()
  })

  // Data arrives async after mount; run the initial fit once the world has a
  // real size (and the viewport has been measured).
  let did_initial_fit = false
  $: if (!did_initial_fit && viewport_el && layout.world.width > 0) {
    did_initial_fit = true
    fit()
  }

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
<div
  bind:this={viewport_el}
  class="relative overflow-hidden h-full w-full bg-gray-50 select-none touch-none {panning
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
            <Float placement="bottom" offset_px={10} portal={true} role="none">
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
</div>
