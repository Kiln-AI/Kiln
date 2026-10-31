// @vitest-environment jsdom
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest"
import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"
import type { ProviderModels } from "$lib/types"
import {
  build_lineage_graph,
  type FilterKey,
  type LineageGraph,
} from "$lib/utils/lineage/lineage_graph"
import {
  layout_lineage,
  type LineageLayout,
} from "$lib/utils/lineage/lineage_layout"
import { make_dated_config } from "$lib/utils/lineage/__tests__/lineage_fixtures"
import LineageCanvas from "./lineage_canvas.svelte"

const VIEW = { width: 800, height: 600 }

// jsdom does no layout, so every element reports the same size: an 800 by
// 600 view unless a test narrows it. jsdom has no pointer capture either.
let view_size = { ...VIEW }

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => view_size.width,
  })
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get: () => view_size.height,
  })
  Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {
    configurable: true,
    value: () => {},
  })
})

afterAll(() => {
  // These shadow Element's own; removing them restores those.
  Reflect.deleteProperty(HTMLElement.prototype, "clientWidth")
  Reflect.deleteProperty(HTMLElement.prototype, "clientHeight")
  Reflect.deleteProperty(HTMLElement.prototype, "setPointerCapture")
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  view_size = { ...VIEW }
})

const MODEL_INFO: ProviderModels = {
  models: {
    gpt_5: { id: "gpt_5", name: "GPT 5" },
    gpt_5_mini: { id: "gpt_5_mini", name: "GPT 5 Mini" },
  },
}

// root ─┬─ a (prompt) ─┐
//       └─ b (copy) ┄┄┄┴─ c (model), with b as an extra parent of c
// grid: no recorded parent
function make_graph(): LineageGraph {
  return build_lineage_graph([
    make_dated_config("root", 0),
    make_dated_config("a", 1, ["root"], { prompt_id: "other_prompt" }),
    make_dated_config("b", 2, ["root"]),
    make_dated_config("c", 3, ["a", "b"], {
      prompt_id: "other_prompt",
      model_name: "gpt_5_mini",
    }),
    make_dated_config("grid", 4),
  ])
}

interface RenderOptions {
  filters?: Set<FilterKey>
  selected_id?: string | null
  initial_center_id?: string | null
}

function render_canvas(options: RenderOptions = {}) {
  const graph = make_graph()
  const layout = layout_lineage(graph)
  const result = render(LineageCanvas, {
    props: {
      graph,
      layout,
      filters: options.filters ?? new Set<FilterKey>(),
      selected_id: options.selected_id ?? null,
      initial_center_id: options.initial_center_id ?? null,
      model_info: MODEL_INFO,
    },
  })
  const canvas = result.container.querySelector(
    '[aria-label="Run config lineage graph"]',
  ) as HTMLElement
  const select = vi.fn()
  const close = vi.fn()
  result.component.$on("select", (event: CustomEvent<string>) =>
    select(event.detail),
  )
  result.component.$on("close", close)
  return { ...result, graph, layout, canvas, select, close }
}

function node_el(container: HTMLElement, id: string): SVGGElement {
  const el = container.querySelector(`[data-node-id="${id}"]`)
  if (!el) {
    throw new Error(`no node ${id}`)
  }
  return el as SVGGElement
}

// The node's hit target, which is what the pointer lands on.
function hit_target(container: HTMLElement, id: string): Element {
  return node_el(container, id).lastElementChild as Element
}

function zoom_label(container: HTMLElement): string {
  return (
    container.querySelector('[data-testid="lineage-zoom-label"]')
      ?.textContent ?? ""
  )
}

function world_transform(container: HTMLElement): string {
  return container.querySelector("svg > g")?.getAttribute("transform") ?? ""
}

function button(container: HTMLElement, label: string): HTMLButtonElement {
  return container.querySelector(
    `button[aria-label="${label}"]`,
  ) as HTMLButtonElement
}

async function rendered_and_sized(options: RenderOptions = {}) {
  const result = render_canvas(options)
  await waitFor(() =>
    expect(world_transform(result.container)).not.toBe(
      "translate(0 0) scale(1)",
    ),
  )
  return result
}

// Svelte measures the canvas through a hidden iframe's resize event.
async function resize_view(container: HTMLElement, width: number) {
  view_size = { ...view_size, width }
  container
    .querySelector("iframe")
    ?.contentWindow?.dispatchEvent(new Event("resize"))
  await tick()
}

function parse_transform(transform: string): {
  tx: number
  ty: number
  k: number
} {
  const match = /translate\((\S+) (\S+)\) scale\((\S+)\)/.exec(transform)
  if (!match) {
    throw new Error(`unexpected transform ${transform}`)
  }
  return { tx: Number(match[1]), ty: Number(match[2]), k: Number(match[3]) }
}

function edge_d(layout: LineageLayout, id: string): string {
  const edge = layout.edges.find((e) => e.id === id)
  if (!edge) {
    throw new Error(`no edge ${id}`)
  }
  return edge.d
}

function path_d(container: HTMLElement, testid: string): string {
  return (
    container.querySelector(`[data-testid="${testid}"]`)?.getAttribute("d") ??
    ""
  )
}

// Watches every node's element and its children. The returned function stops
// watching and gives every change seen. Records reach the callback in a
// microtask, so an await can deliver some; takeRecords() picks up the rest.
function watch_nodes(container: HTMLElement): () => MutationRecord[] {
  const records: MutationRecord[] = []
  const observer = new MutationObserver((batch) => records.push(...batch))
  for (const el of container.querySelectorAll("[data-node-id]")) {
    observer.observe(el, {
      attributes: true,
      childList: true,
      characterData: true,
      subtree: true,
    })
  }
  return () => {
    records.push(...observer.takeRecords())
    observer.disconnect()
    return records
  }
}

async function hover(container: HTMLElement, id: string) {
  await fireEvent.pointerOver(hit_target(container, id))
  vi.advanceTimersByTime(100)
  await tick()
}

function empty_space(container: HTMLElement): SVGSVGElement {
  return container.querySelector("svg") as SVGSVGElement
}

async function click(target: Element, at = { x: 10, y: 10 }) {
  await fireEvent.pointerDown(target, {
    button: 0,
    pointerId: 1,
    clientX: at.x,
    clientY: at.y,
  })
  await fireEvent.pointerUp(target, {
    pointerId: 1,
    clientX: at.x,
    clientY: at.y,
  })
}

describe("LineageCanvas", () => {
  it("renders one node per graph node and the grid label", () => {
    const { container, graph } = render_canvas()
    const ids = [...container.querySelectorAll("[data-node-id]")].map((el) =>
      el.getAttribute("data-node-id"),
    )
    expect(ids.sort()).toEqual([...graph.nodes.keys()].sort())
    expect(container.querySelector("text")?.textContent).toBe(
      "No recorded parent (1)",
    )
  })

  it("selects a node on click", async () => {
    const { container, select } = render_canvas()
    await click(hit_target(container, "a"))
    expect(select).toHaveBeenCalledWith("a")
  })

  it("pans instead of selecting when the pointer drags", async () => {
    const { container, canvas, select } = await rendered_and_sized()
    const before = world_transform(container)
    const target = hit_target(container, "a")
    await fireEvent.pointerDown(target, {
      button: 0,
      pointerId: 1,
      clientX: 10,
      clientY: 10,
    })
    await fireEvent.pointerMove(canvas, {
      pointerId: 1,
      clientX: 20,
      clientY: 10,
    })
    await fireEvent.pointerUp(canvas, {
      pointerId: 1,
      clientX: 20,
      clientY: 10,
    })
    expect(select).not.toHaveBeenCalled()
    expect(world_transform(container)).not.toBe(before)
  })

  it("doesn't select anything on a click on empty space", async () => {
    vi.useFakeTimers()
    const { container, select, close } = render_canvas()
    await click(empty_space(container))
    vi.advanceTimersByTime(1000)
    expect(select).not.toHaveBeenCalled()
    expect(close).not.toHaveBeenCalled()
  })

  it("deselects a short wait after a click on empty space", async () => {
    vi.useFakeTimers()
    const { container, close } = render_canvas({ selected_id: "a" })
    await click(empty_space(container))
    vi.advanceTimersByTime(200)
    expect(close).not.toHaveBeenCalled()
    vi.advanceTimersByTime(50)
    expect(close).toHaveBeenCalledTimes(1)
  })

  it("keeps the selection when a click on empty space turns into a double-click", async () => {
    vi.useFakeTimers()
    const { container, canvas, close } = render_canvas({ selected_id: "a" })
    await click(empty_space(container))
    vi.advanceTimersByTime(100)
    await click(empty_space(container))
    await fireEvent.dblClick(canvas)
    vi.advanceTimersByTime(1000)
    expect(close).not.toHaveBeenCalled()
  })

  it("keeps the selection after a drag on empty space", async () => {
    vi.useFakeTimers()
    const { canvas, close } = render_canvas({ selected_id: "a" })
    await fireEvent.pointerDown(canvas, {
      button: 0,
      pointerId: 1,
      clientX: 10,
      clientY: 10,
    })
    await fireEvent.pointerMove(canvas, {
      pointerId: 1,
      clientX: 30,
      clientY: 10,
    })
    await fireEvent.pointerUp(canvas, {
      pointerId: 1,
      clientX: 30,
      clientY: 10,
    })
    vi.advanceTimersByTime(1000)
    expect(close).not.toHaveBeenCalled()
  })

  it("dims nodes that don't match the filters, except the selected one", () => {
    const { container } = render_canvas({
      filters: new Set<FilterKey>(["prompt"]),
      selected_id: "b",
    })
    const opacity = (id: string) =>
      node_el(container, id).getAttribute("opacity")
    expect(opacity("a")).toBe("1")
    expect(opacity("b")).toBe("1")
    expect(opacity("c")).toBe("0.15")
    expect(opacity("root")).toBe("0.15")
    expect(opacity("grid")).toBe("0.15")
  })

  it("dims nothing without filters", () => {
    const { container, graph } = render_canvas()
    for (const id of graph.nodes.keys()) {
      expect(node_el(container, id).getAttribute("opacity")).toBe("1")
    }
  })

  it("highlights every edge above the selected node and rings it", () => {
    const { container, layout } = render_canvas({ selected_id: "c" })
    const highlighted = path_d(container, "lineage-highlighted-edges")
    for (const id of ["root->a", "root->b", "a->c", "b->c"]) {
      expect(highlighted).toContain(edge_d(layout, id))
    }
    expect(
      container.querySelector('[data-testid="lineage-selection-ring"]'),
    ).not.toBeNull()
  })

  it("highlights nothing and draws no ring without a selection", () => {
    const { container } = render_canvas()
    expect(path_d(container, "lineage-highlighted-edges")).toBe("")
    expect(
      container.querySelector('[data-testid="lineage-selection-ring"]'),
    ).toBeNull()
  })

  it("highlights only the edges above the selected node", () => {
    const { container, layout } = render_canvas({ selected_id: "a" })
    expect(path_d(container, "lineage-highlighted-edges")).toBe(
      edge_d(layout, "root->a"),
    )
  })

  it("draws a hovered node's edges to its parents and children dark", async () => {
    vi.useFakeTimers()
    const { container, layout } = render_canvas()
    const hovered = () => path_d(container, "lineage-hovered-edges")
    await fireEvent.pointerOver(hit_target(container, "b"))
    expect(hovered()).toBe("")
    vi.advanceTimersByTime(100)
    await tick()
    expect(hovered()).toBe(edge_d(layout, "root->b") + edge_d(layout, "b->c"))
    await fireEvent.pointerOut(hit_target(container, "b"), {
      relatedTarget: container.querySelector("svg"),
    })
    expect(hovered()).toBe("")
  })

  it("draws a hovered merge's edges from both its parents", async () => {
    vi.useFakeTimers()
    const { container, layout } = render_canvas()
    await hover(container, "c")
    expect(path_d(container, "lineage-hovered-edges")).toBe(
      edge_d(layout, "a->c") + edge_d(layout, "b->c"),
    )
  })

  // Hover must stay cheap at 1,000 nodes. This catches hover state that changes
  // a node's markup, not a re-run of the node block that yields the same values.
  it("leaves every node's markup untouched on hover", async () => {
    vi.useFakeTimers()
    const { container } = render_canvas()
    const node_changes = watch_nodes(container)
    await hover(container, "b")
    expect(path_d(container, "lineage-hovered-edges")).not.toBe("")
    expect(node_changes()).toEqual([])
  })

  it("changes node markup when the filters change", async () => {
    const { container, component } = render_canvas()
    const node_changes = watch_nodes(container)
    component.$set({ filters: new Set<FilterKey>(["prompt"]) })
    await tick()
    expect(node_changes().length).toBeGreaterThan(0)
  })

  it("fits the graph on load, which caps the zoom at 100%", async () => {
    const { container, layout } = await rendered_and_sized()
    expect(zoom_label(container)).toBe("100%")
    expect(world_transform(container)).toBe(
      `translate(${(VIEW.width - layout.width) / 2} ${(VIEW.height - layout.height) / 2}) scale(1)`,
    )
  })

  it("centers the initial node at 100% when one is given", async () => {
    const { container, layout } = await rendered_and_sized({
      initial_center_id: "c",
    })
    const pos = layout.positions.get("c") as { x: number; y: number }
    expect(world_transform(container)).toBe(
      `translate(${VIEW.width / 2 - (pos.x + 7)} ${VIEW.height / 2 - (pos.y + 7)}) scale(1)`,
    )
  })

  it("zooms with the toolbar buttons and fits again", async () => {
    const { container } = await rendered_and_sized()
    await fireEvent.click(button(container, "Zoom in"))
    expect(zoom_label(container)).toBe("125%")
    await fireEvent.click(button(container, "Zoom out"))
    await fireEvent.click(button(container, "Zoom out"))
    expect(zoom_label(container)).toBe("80%")
    await fireEvent.click(button(container, "Fit graph"))
    expect(zoom_label(container)).toBe("100%")
  })

  it("zooms with the +, - and 0 keys", async () => {
    const { container, canvas } = await rendered_and_sized()
    await fireEvent.keyDown(canvas, { key: "+" })
    await fireEvent.keyDown(canvas, { key: "=" })
    expect(zoom_label(container)).toBe("156%")
    await fireEvent.keyDown(canvas, { key: "-" })
    expect(zoom_label(container)).toBe("125%")
    await fireEvent.keyDown(canvas, { key: "0" })
    expect(zoom_label(container)).toBe("100%")
  })

  it("zooms with Ctrl and the wheel, and pans with a plain wheel", async () => {
    const { container, canvas } = await rendered_and_sized()
    await fireEvent.wheel(canvas, { deltaY: -100, ctrlKey: true })
    expect(zoom_label(container)).toBe("165%")
    const before = world_transform(container)
    await fireEvent.wheel(canvas, { deltaY: 30 })
    expect(zoom_label(container)).toBe("165%")
    expect(world_transform(container)).not.toBe(before)
  })

  it("zooms in one step about the cursor on a double-click", async () => {
    const { container, canvas } = await rendered_and_sized()
    const cursor = { x: 120, y: 90 }
    const before = parse_transform(world_transform(container))
    await fireEvent.dblClick(canvas, { clientX: cursor.x, clientY: cursor.y })
    const after = parse_transform(world_transform(container))
    expect(zoom_label(container)).toBe("125%")
    expect((cursor.x - after.tx) / after.k).toBeCloseTo(
      (cursor.x - before.tx) / before.k,
    )
    expect((cursor.y - after.ty) / after.k).toBeCloseTo(
      (cursor.y - before.ty) / before.k,
    )
  })

  it("brings a node selected from outside the graph into view", async () => {
    const { container, canvas, component, layout } = await rendered_and_sized()
    // Pans the graph far to the left, so c ends up off screen.
    await fireEvent.wheel(canvas, { deltaX: 600 })
    component.$set({ selected_id: "c" })
    await tick()
    const { tx, ty, k } = parse_transform(world_transform(container))
    const pos = layout.positions.get("c") as { x: number; y: number }
    const left = pos.x * k + tx
    const top = pos.y * k + ty
    expect(left).toBeGreaterThanOrEqual(0)
    expect(left + 14 * k).toBeLessThanOrEqual(VIEW.width)
    expect(top).toBeGreaterThanOrEqual(0)
    expect(top + 14 * k).toBeLessThanOrEqual(VIEW.height)
  })

  it("focuses the graph on request", () => {
    const { canvas, component } = render_canvas()
    component.focus_graph()
    expect(document.activeElement).toBe(canvas)
  })

  it("dispatches close on Escape and marks the key handled", async () => {
    const { canvas, close } = render_canvas({ selected_id: "a" })
    let handled = false
    const listener = (event: Event) => (handled = event.defaultPrevented)
    window.addEventListener("keydown", listener)
    await fireEvent.keyDown(canvas, { key: "Escape" })
    window.removeEventListener("keydown", listener)
    expect(close).toHaveBeenCalledTimes(1)
    expect(handled).toBe(true)
  })

  it("keeps the center in place when the view narrows with nothing selected", async () => {
    const { container } = await rendered_and_sized()
    const before = parse_transform(world_transform(container))
    await resize_view(container, 400)
    expect(parse_transform(world_transform(container))).toEqual({
      ...before,
      tx: before.tx - 200,
    })
  })

  it("keeps the selected node on screen when the view narrows", async () => {
    const { container, canvas, layout } = await rendered_and_sized({
      selected_id: "c",
    })
    // Pans c toward the right edge, where narrowing the view by 400px about
    // its center would push it off screen.
    await fireEvent.wheel(canvas, { deltaX: -350 })
    await resize_view(container, 400)
    const { tx, k } = parse_transform(world_transform(container))
    const pos = layout.positions.get("c") as { x: number; y: number }
    const left = pos.x * k + tx
    expect(left).toBeGreaterThanOrEqual(24)
    expect(left + 14 * k).toBeLessThanOrEqual(400 - 24)
  })

  it("selects the oldest starting point on an arrow key with no selection", async () => {
    const { canvas, select } = render_canvas()
    await fireEvent.keyDown(canvas, { key: "ArrowDown" })
    expect(select).toHaveBeenCalledWith("root")
  })

  it("picks the parent, the neighbor and the child of the selected node with the arrow keys", async () => {
    const { canvas, select } = render_canvas({ selected_id: "a" })
    await fireEvent.keyDown(canvas, { key: "ArrowUp" })
    expect(select).toHaveBeenLastCalledWith("root")
    await fireEvent.keyDown(canvas, { key: "ArrowRight" })
    expect(select).toHaveBeenLastCalledWith("b")
    await fireEvent.keyDown(canvas, { key: "ArrowDown" })
    expect(select).toHaveBeenLastCalledWith("c")
  })

  it("ignores keys pressed with ⌘, Ctrl or Alt", async () => {
    const { container, canvas, select } = await rendered_and_sized({
      selected_id: "a",
    })
    await fireEvent.keyDown(canvas, { key: "ArrowUp", metaKey: true })
    await fireEvent.keyDown(canvas, { key: "0", ctrlKey: true })
    await fireEvent.keyDown(canvas, { key: "+", altKey: true })
    expect(select).not.toHaveBeenCalled()
    expect(zoom_label(container)).toBe("100%")
  })

  it("shows the tooltip after a short hover and hides it on leave", async () => {
    vi.useFakeTimers()
    const { container } = render_canvas()
    const tooltip = () =>
      container.querySelector('[data-testid="lineage-tooltip"]')
    await fireEvent.pointerOver(hit_target(container, "c"))
    expect(tooltip()).toBeNull()
    vi.advanceTimersByTime(100)
    await tick()
    const lines = [...(tooltip()?.children ?? [])].map((el) =>
      el.textContent?.trim(),
    )
    expect(lines).toEqual(["Name c", "Model", "GPT 5 Mini (OpenAI)"])
    await fireEvent.pointerOut(hit_target(container, "c"), {
      relatedTarget: container.querySelector("svg"),
    })
    expect(tooltip()).toBeNull()
  })

  it("announces the selected node", () => {
    const { container } = render_canvas({ selected_id: "a" })
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toBe(
      "Name a. Prompt.",
    )
  })
})
