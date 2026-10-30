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
    const { container, select } = render_canvas()
    await click(container.querySelector("svg") as SVGSVGElement)
    expect(select).not.toHaveBeenCalled()
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
    const path = (id: string) =>
      container.querySelector(`[data-testid="${id}"]`)?.getAttribute("d") ?? ""
    const primary = path("lineage-highlighted-primary")
    for (const id of ["root->a", "root->b", "a->c"]) {
      expect(primary).toContain(edge_d(layout, id))
    }
    expect(path("lineage-highlighted-extra")).toBe(edge_d(layout, "b->c"))
    expect(
      container.querySelector('[data-testid="lineage-selection-ring"]'),
    ).not.toBeNull()
  })

  it("highlights nothing and draws no ring without a selection", () => {
    const { container } = render_canvas()
    expect(
      container
        .querySelector('[data-testid="lineage-highlighted-primary"]')
        ?.getAttribute("d"),
    ).toBe("")
    expect(
      container.querySelector('[data-testid="lineage-selection-ring"]'),
    ).toBeNull()
  })

  it("highlights only the edges above the selected node", () => {
    const { container, layout } = render_canvas({ selected_id: "a" })
    const path = (id: string) =>
      container.querySelector(`[data-testid="${id}"]`)?.getAttribute("d") ?? ""
    expect(path("lineage-highlighted-primary")).toBe(edge_d(layout, "root->a"))
    expect(path("lineage-highlighted-extra")).toBe("")
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

  it("fits on a double-click on empty space", async () => {
    const { container, canvas } = await rendered_and_sized()
    await fireEvent.click(button(container, "Zoom in"))
    const svg = container.querySelector("svg") as SVGSVGElement
    await click(svg)
    await fireEvent.dblClick(canvas)
    expect(zoom_label(container)).toBe("100%")
  })

  it("doesn't fit on a double-click on a node", async () => {
    const { container, canvas } = await rendered_and_sized()
    await fireEvent.click(button(container, "Zoom in"))
    await click(hit_target(container, "a"))
    await fireEvent.dblClick(canvas)
    expect(zoom_label(container)).toBe("125%")
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
