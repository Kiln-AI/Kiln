<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount } from "svelte"
  import type { ProviderModels } from "$lib/types"
  import Float from "$lib/ui/float.svelte"
  import {
    node_model_text,
    node_title,
    status_text,
  } from "$lib/utils/lineage/lineage_display"
  import {
    ancestor_edge_ids,
    node_matches_filters,
    type FilterKey,
    type LineageGraph,
  } from "$lib/utils/lineage/lineage_graph"
  import { GLYPH } from "$lib/utils/lineage/lineage_glyph"
  import {
    edge_path_groups,
    join_edge_paths,
    type LineageLayout,
  } from "$lib/utils/lineage/lineage_layout"
  import {
    next_selection,
    type NavKey,
  } from "$lib/utils/lineage/lineage_navigation"
  import {
    center_on,
    clamp_viewport,
    ensure_visible,
    fit,
    pan_by,
    resize_keep_center,
    wheel_delta_px,
    wheel_zoom_factor,
    zoom_at,
    zoom_step,
    type Point,
    type Rect,
    type Size,
    type Viewport,
  } from "$lib/utils/lineage/lineage_viewport"
  import LineageGlyph from "./lineage_glyph.svelte"

  export let graph: LineageGraph
  export let layout: LineageLayout
  export let filters: ReadonlySet<FilterKey>
  export let selected_id: string | null
  // Read once, when the view first has a size: the run config to center on at
  // 100% instead of fitting the whole graph.
  export let initial_center_id: string | null = null
  export let model_info: ProviderModels | null

  const dispatch = createEventDispatcher<{ select: string; close: null }>()

  const NODE_SIZE = GLYPH.graph.size
  const DRAG_THRESHOLD_PX = 4
  const HOVER_DELAY_MS = 100
  // Long enough for a second click to make it a double-click, which zooms
  // instead of deselecting.
  const DESELECT_DELAY_MS = 250
  const DIMMED_OPACITY = 0.15
  const NAV_KEYS: readonly string[] = [
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
  ]

  let canvas_el: HTMLDivElement
  let view_width = 0
  let view_height = 0
  let vp: Viewport = { k: 1, tx: 0, ty: 0 }

  $: world = { width: layout.width, height: layout.height }
  $: view = { width: view_width, height: view_height }
  $: nodes = [...graph.nodes.values()]
  $: highlighted = selected_id
    ? ancestor_edge_ids(graph, selected_id)
    : new Set<string>()
  $: edge_paths = edge_path_groups(layout.edges, highlighted)
  $: selected_node = selected_id ? graph.nodes.get(selected_id) : undefined
  $: selected_pos = selected_id ? layout.positions.get(selected_id) : undefined
  $: announcement = selected_node
    ? `${node_title(selected_node)}. ${status_text(selected_node.status)}.`
    : ""

  let initialized = false
  let last_view: Size = { width: 0, height: 0 }
  let last_layout: LineageLayout | null = null

  $: sync_viewport(layout, view_width, view_height)
  // Brings a newly selected node into view, such as one chosen from the panel.
  // A clicked node is already on screen, so at most it shifts in from the edge.
  $: reveal(selected_id)

  function reveal(id: string | null) {
    const pos = id && initialized ? layout.positions.get(id) : undefined
    if (pos) {
      vp = ensure_visible(vp, node_rect(pos), world, view)
    }
  }

  export function focus_graph() {
    canvas_el.focus()
  }

  function sync_viewport(
    next_layout: LineageLayout,
    width: number,
    height: number,
  ) {
    if (width <= 0 || height <= 0) {
      return
    }
    const next_view = { width, height }
    const next_world = { width: next_layout.width, height: next_layout.height }
    if (!initialized) {
      if (next_world.width <= 0) {
        return
      }
      vp = initial_viewport(next_layout, next_world, next_view)
      initialized = true
    } else if (width !== last_view.width || height !== last_view.height) {
      vp = keep_selected_visible(
        resize_keep_center(vp, last_view, next_view),
        next_layout,
        next_world,
        next_view,
      )
    } else if (next_layout !== last_layout) {
      vp = clamp_viewport(vp, next_world, next_view)
    }
    last_view = next_view
    last_layout = next_layout
  }

  function initial_viewport(
    initial_layout: LineageLayout,
    initial_world: Size,
    initial_view: Size,
  ): Viewport {
    const pos = initial_center_id
      ? initial_layout.positions.get(initial_center_id)
      : undefined
    if (!pos) {
      return fit(initial_world, initial_view)
    }
    return center_on(
      { x: pos.x + NODE_SIZE / 2, y: pos.y + NODE_SIZE / 2 },
      1,
      initial_world,
      initial_view,
    )
  }

  // Opening the panel narrows the view, which can push the node just selected
  // off screen.
  function keep_selected_visible(
    next: Viewport,
    next_layout: LineageLayout,
    next_world: Size,
    next_view: Size,
  ): Viewport {
    const pos = selected_id ? next_layout.positions.get(selected_id) : undefined
    return pos
      ? ensure_visible(next, node_rect(pos), next_world, next_view)
      : next
  }

  function node_rect(pos: Point): Rect {
    return { x: pos.x, y: pos.y, w: NODE_SIZE, h: NODE_SIZE }
  }

  function set_viewport(next: Viewport) {
    vp = next
    hide_tooltip()
  }

  function zoom_by_step(direction: 1 | -1) {
    set_viewport(zoom_step(vp, direction, world, view))
  }

  function fit_view() {
    set_viewport(fit(world, view))
  }

  function view_point(event: { clientX: number; clientY: number }): Point {
    const rect = canvas_el.getBoundingClientRect()
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }

  function node_id_at(target: EventTarget | null): string | null {
    if (!(target instanceof Element)) {
      return null
    }
    return (
      target.closest("[data-node-id]")?.getAttribute("data-node-id") ?? null
    )
  }

  let hover_id: string | null = null
  let hover_timer: ReturnType<typeof setTimeout> | null = null

  $: hover_node = hover_id ? graph.nodes.get(hover_id) : undefined
  $: hover_pos = hover_id ? layout.positions.get(hover_id) : undefined
  // Drawn over the other edges instead of moving them into another group, so a
  // hover redraws only these few edges.
  $: hover_paths = join_edge_paths(
    hover_id ? layout.node_edges.get(hover_id) ?? [] : [],
  )

  function clear_hover_timer() {
    if (hover_timer !== null) {
      clearTimeout(hover_timer)
      hover_timer = null
    }
  }

  function schedule_hover(node_id: string | null) {
    clear_hover_timer()
    if (node_id === null) {
      hover_id = null
    } else if (node_id !== hover_id) {
      hover_timer = setTimeout(() => {
        hover_id = node_id
        hover_timer = null
      }, HOVER_DELAY_MS)
    }
  }

  function hide_tooltip() {
    schedule_hover(null)
  }

  function on_pointerover(event: PointerEvent) {
    if (dragging) {
      return
    }
    const node_id = node_id_at(event.target)
    if (node_id !== null) {
      schedule_hover(node_id)
    }
  }

  function on_pointerout(event: PointerEvent) {
    if (node_id_at(event.relatedTarget) === null) {
      hide_tooltip()
    }
  }

  interface PointerDrag {
    pointer_id: number
    start: Point
    last: Point
    node_id: string | null
  }

  let drag: PointerDrag | null = null
  let dragging = false
  let deselect_timer: ReturnType<typeof setTimeout> | null = null

  function cancel_deselect() {
    if (deselect_timer !== null) {
      clearTimeout(deselect_timer)
      deselect_timer = null
    }
  }

  function schedule_deselect() {
    cancel_deselect()
    deselect_timer = setTimeout(() => {
      deselect_timer = null
      dispatch("close")
    }, DESELECT_DELAY_MS)
  }

  function on_pointerdown(event: PointerEvent) {
    if (event.button !== 0) {
      return
    }
    cancel_deselect()
    const node_id = node_id_at(event.target)
    const point = { x: event.clientX, y: event.clientY }
    drag = { pointer_id: event.pointerId, start: point, last: point, node_id }
    // Keeps the drag going when the pointer leaves the canvas.
    canvas_el.setPointerCapture(event.pointerId)
  }

  function on_pointermove(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointer_id) {
      return
    }
    const point = { x: event.clientX, y: event.clientY }
    if (!dragging) {
      const moved = Math.hypot(point.x - drag.start.x, point.y - drag.start.y)
      if (moved <= DRAG_THRESHOLD_PX) {
        return
      }
      dragging = true
    }
    set_viewport(
      pan_by(vp, point.x - drag.last.x, point.y - drag.last.y, world, view),
    )
    drag.last = point
  }

  function on_pointerup(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointer_id) {
      return
    }
    if (!dragging) {
      if (drag.node_id !== null) {
        dispatch("select", drag.node_id)
      } else if (selected_id !== null) {
        schedule_deselect()
      }
    }
    end_drag()
  }

  function end_drag() {
    drag = null
    dragging = false
  }

  function on_dblclick(event: MouseEvent) {
    cancel_deselect()
    set_viewport(zoom_step(vp, 1, world, view, view_point(event)))
  }

  function on_wheel(event: WheelEvent) {
    event.preventDefault()
    const dx = wheel_delta_px(event.deltaX, event.deltaMode, view_height)
    const dy = wheel_delta_px(event.deltaY, event.deltaMode, view_height)
    if (event.ctrlKey || event.metaKey) {
      const k = vp.k * wheel_zoom_factor(dy)
      set_viewport(zoom_at(vp, view_point(event), k, world, view))
    } else {
      set_viewport(pan_by(vp, -dx, -dy, world, view))
    }
  }

  // Safari reports a trackpad pinch as gesture events, which aren't in the DOM
  // typings and which Svelte can't bind with on:.
  type GestureEventLike = Event & {
    scale: number
    clientX: number
    clientY: number
  }

  onMount(() => {
    let start_k = vp.k
    const on_gesturestart = (event: Event) => {
      event.preventDefault()
      start_k = vp.k
    }
    const on_gesturechange = (event: Event) => {
      event.preventDefault()
      const gesture = event as GestureEventLike
      set_viewport(
        zoom_at(vp, view_point(gesture), start_k * gesture.scale, world, view),
      )
    }
    canvas_el.addEventListener("gesturestart", on_gesturestart)
    canvas_el.addEventListener("gesturechange", on_gesturechange)
    return () => {
      canvas_el.removeEventListener("gesturestart", on_gesturestart)
      canvas_el.removeEventListener("gesturechange", on_gesturechange)
    }
  })

  onDestroy(() => {
    clear_hover_timer()
    cancel_deselect()
  })

  function is_nav_key(key: string): key is NavKey {
    return NAV_KEYS.includes(key)
  }

  function move_selection(key: NavKey) {
    const next = next_selection(graph, layout, selected_id, key)
    if (next === null || next === selected_id) {
      return
    }
    dispatch("select", next)
    const pos = layout.positions.get(next)
    if (pos) {
      set_viewport(ensure_visible(vp, node_rect(pos), world, view))
    }
  }

  function on_keydown(event: KeyboardEvent) {
    // Leaves the browser's own shortcuts alone, such as ⌘+ and Ctrl+0.
    if (event.ctrlKey || event.metaKey || event.altKey) {
      return
    }
    if (is_nav_key(event.key)) {
      event.preventDefault()
      move_selection(event.key)
      return
    }
    switch (event.key) {
      case "Escape":
        event.preventDefault()
        dispatch("close")
        return
      case "+":
      case "=":
        event.preventDefault()
        zoom_by_step(1)
        return
      case "-":
        event.preventDefault()
        zoom_by_step(-1)
        return
      case "0":
        event.preventDefault()
        fit_view()
        return
    }
  }
</script>

<div class="h-full rounded-lg border flex flex-col overflow-hidden">
  <div class="flex items-center justify-between gap-3 px-3 py-2 border-b">
    <div class="text-xs text-gray-500">
      Click a run config for details. Hover for a summary.
    </div>
    <div class="join shrink-0">
      <button
        type="button"
        class="btn btn-sm join-item"
        aria-label="Zoom out"
        on:click={() => zoom_by_step(-1)}>−</button
      >
      <span
        class="btn btn-sm join-item no-animation pointer-events-none min-w-14 tabular-nums"
        data-testid="lineage-zoom-label">{Math.round(vp.k * 100)}%</span
      >
      <button
        type="button"
        class="btn btn-sm join-item"
        aria-label="Zoom in"
        on:click={() => zoom_by_step(1)}>+</button
      >
      <button
        type="button"
        class="btn btn-sm join-item"
        aria-label="Fit graph"
        on:click={fit_view}>Fit</button
      >
    </div>
  </div>
  <!-- One focusable widget with its own pointer and keyboard handling, which is
       what role="application" describes; Svelte counts that role as static. -->
  <!-- svelte-ignore a11y-no-noninteractive-tabindex a11y-no-noninteractive-element-interactions -->
  <div
    bind:this={canvas_el}
    bind:clientWidth={view_width}
    bind:clientHeight={view_height}
    class="relative flex-1 min-h-0 overflow-hidden select-none touch-none focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary {dragging
      ? 'cursor-grabbing'
      : 'cursor-grab'}"
    tabindex="0"
    role="application"
    aria-label="Run config lineage graph"
    on:pointerdown={on_pointerdown}
    on:pointermove={on_pointermove}
    on:pointerup={on_pointerup}
    on:pointercancel={end_drag}
    on:pointerover={on_pointerover}
    on:pointerout={on_pointerout}
    on:wheel|nonpassive={on_wheel}
    on:dblclick={on_dblclick}
    on:keydown={on_keydown}
  >
    <svg class="absolute inset-0 w-full h-full" aria-hidden="true">
      <defs>
        <!-- In user space rather than objectBoundingBox: the outline glyphs
             are inset by half a pixel, so a box clip would cut their stroke. -->
        <clipPath id="lineage-node-clip" clipPathUnits="userSpaceOnUse">
          <rect
            width={NODE_SIZE}
            height={NODE_SIZE}
            rx={GLYPH.graph.radius}
            ry={GLYPH.graph.radius}
          />
        </clipPath>
      </defs>
      <g transform="translate({vp.tx} {vp.ty}) scale({vp.k})">
        <path
          d={edge_paths.resting.primary}
          class="stroke-base-300"
          stroke-width="1"
          fill="none"
          vector-effect="non-scaling-stroke"
        />
        <path
          d={edge_paths.resting.extra}
          class="stroke-base-300/60"
          stroke-width="0.75"
          fill="none"
          vector-effect="non-scaling-stroke"
        />
        <path
          d={edge_paths.highlighted.primary + edge_paths.highlighted.extra}
          class="stroke-secondary"
          stroke-width="1.5"
          fill="none"
          vector-effect="non-scaling-stroke"
          data-testid="lineage-highlighted-edges"
        />
        <path
          d={hover_paths.primary + hover_paths.extra}
          class="stroke-secondary"
          stroke-width="1.5"
          fill="none"
          vector-effect="non-scaling-stroke"
          data-testid="lineage-hovered-edges"
        />
        {#if layout.grid_label}
          <text
            x={layout.grid_label.x}
            y={layout.grid_label.y}
            class="text-xs fill-gray-500"
            >No recorded parent ({graph.no_parent_ids.length})</text
          >
        {/if}
        {#each nodes as node (node.id)}
          {@const pos = layout.positions.get(node.id)}
          {#if pos}
            <g
              transform="translate({pos.x} {pos.y})"
              data-node-id={node.id}
              opacity={node.id !== selected_id &&
              !node_matches_filters(node.status, filters)
                ? DIMMED_OPACITY
                : 1}
              class="cursor-pointer"
            >
              <g clip-path="url(#lineage-node-clip)">
                <LineageGlyph status={node.status} glyph={GLYPH.graph} />
              </g>
              <!-- One hit target per node, so moving across the gaps between
                   segments doesn't leave and re-enter the node. -->
              <rect width={NODE_SIZE} height={NODE_SIZE} fill="transparent" />
            </g>
          {/if}
        {/each}
        {#if selected_pos}
          <g data-testid="lineage-selection-ring" pointer-events="none">
            <rect
              x={selected_pos.x - 1}
              y={selected_pos.y - 1}
              width={NODE_SIZE + 2}
              height={NODE_SIZE + 2}
              rx={GLYPH.graph.radius + 1}
              class="stroke-base-100"
              stroke-width="2"
              fill="none"
            />
            <rect
              x={selected_pos.x - 2.75}
              y={selected_pos.y - 2.75}
              width={NODE_SIZE + 5.5}
              height={NODE_SIZE + 5.5}
              rx={GLYPH.graph.radius + 2.75}
              class="stroke-secondary"
              stroke-width="1.5"
              fill="none"
            />
          </g>
        {/if}
      </g>
    </svg>
    {#if hover_node && hover_pos}
      {@const model_text = node_model_text(hover_node, model_info)}
      <div
        class="absolute pointer-events-none"
        style="left: {hover_pos.x * vp.k + vp.tx}px; top: {hover_pos.y * vp.k +
          vp.ty}px; width: {NODE_SIZE * vp.k}px; height: {NODE_SIZE * vp.k}px;"
      >
        {#key hover_id}
          <Float placement="right" offset_px={8} role="tooltip">
            <div
              class="w-max max-w-72 px-3 py-2 text-sm text-left text-base-content bg-stone-200 rounded-md shadow-lg flex flex-col"
              data-testid="lineage-tooltip"
            >
              <div class="font-medium truncate">{node_title(hover_node)}</div>
              <div>{status_text(hover_node.status)}</div>
              {#if model_text}
                <div>{model_text}</div>
              {/if}
            </div>
          </Float>
        {/key}
      </div>
    {/if}
    <div class="sr-only" aria-live="polite">{announcement}</div>
  </div>
</div>
