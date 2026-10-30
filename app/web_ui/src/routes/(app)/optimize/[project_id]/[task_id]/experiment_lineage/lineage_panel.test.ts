// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import type { PromptResponse, TaskRunConfig } from "$lib/types"
import { compare_run_configs_link } from "$lib/utils/link_builder"
import type { DisplayContext } from "$lib/utils/lineage/lineage_display"
import {
  build_lineage_graph,
  type LineageGraph,
} from "$lib/utils/lineage/lineage_graph"
import {
  created_at_for,
  make_agent_config,
  make_dated_config,
} from "$lib/utils/lineage/__tests__/lineage_fixtures"

const { goto } = vi.hoisted(() => ({ goto: vi.fn() }))
vi.mock("$app/navigation", () => ({ goto }))

const LineagePanel = (await import("./lineage_panel.svelte")).default

const PROJECT_ID = "p1"
const TASK_ID = "t1"

const TASK_PROMPTS: PromptResponse = {
  generators: [],
  prompts: [
    { id: "p_new", name: "Kinder Prompt", prompt: "Be kind.", type: "saved" },
  ],
}

const CTX: DisplayContext = {
  model_info: null,
  task_prompts: TASK_PROMPTS,
  project_tools: null,
}

function child_config(): TaskRunConfig {
  return make_agent_config({
    id: "child",
    name: "Gusty Forest",
    created_at: created_at_for(1),
    provenance: {
      derived_from_ids: ["root"],
      notes: "Tried a kinder prompt.",
      origin: "agent",
    },
    properties: { prompt_id: "p_new", temperature: 0.7 },
  })
}

// root ─┬─ child (prompt, settings; has notes) ─┐
//       └─ copy ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┴─ merge
// gone (deleted) ── orphan
function make_graph(): LineageGraph {
  return build_lineage_graph([
    make_dated_config("root", 0),
    child_config(),
    make_dated_config("copy", 2, ["root"]),
    make_dated_config("merge", 3, ["child", "copy"], {
      prompt_id: "p_new",
      temperature: 0.7,
    }),
    make_dated_config("orphan", 4, ["gone"]),
  ])
}

function render_panel(node_id: string) {
  const graph = make_graph()
  const node = graph.nodes.get(node_id)
  if (!node) {
    throw new Error(`no node ${node_id}`)
  }
  const result = render(LineagePanel, {
    props: {
      project_id: PROJECT_ID,
      task_id: TASK_ID,
      node,
      graph,
      ctx: CTX,
      available_tools: {},
    },
  })
  const select = vi.fn()
  const close = vi.fn()
  result.component.$on("select", (event: CustomEvent<string>) =>
    select(event.detail),
  )
  result.component.$on("close", close)
  return { ...result, select, close }
}

function button_named(
  container: HTMLElement,
  text: string,
): HTMLButtonElement | null {
  return (
    [...container.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === text,
    ) ?? null
  )
}

function headers(container: HTMLElement): string[] {
  return [...container.querySelectorAll("h2")].map(
    (h) => h.textContent?.trim() ?? "",
  )
}

function lineage_line(container: HTMLElement): string {
  return (
    container
      .querySelector('[data-testid="lineage-panel-line"]')
      ?.textContent?.replace(/\s+/g, " ")
      .trim() ?? ""
  )
}

afterEach(() => {
  cleanup()
  goto.mockReset()
})

describe("LineagePanel", () => {
  it("shows the name and lineage line in the header", () => {
    const { container } = render_panel("child")
    expect(container.textContent).toContain("Gusty Forest")
    expect(lineage_line(container)).toBe("Derived from Name root · 1 child")
  })

  it("lists each change with the new value and the parent's struck through", () => {
    const { container } = render_panel("child")
    expect(headers(container)).toContain("Changed from Parent")
    const grid = container.querySelector(
      '[data-testid="lineage-change-rows"]',
    ) as HTMLElement
    expect(grid.textContent).toContain("Prompt")
    expect(grid.textContent).toContain("Kinder Prompt")
    expect(grid.textContent).toContain("Settings")
    expect(grid.textContent).toContain("Temperature 0.7")
    const struck = [...grid.querySelectorAll(".line-through")].map((el) =>
      el.textContent?.trim(),
    )
    expect(struck).toEqual(["simple_prompt_builder", "Temperature 1"])
  })

  it("says a copy has the same settings as its parent", () => {
    const { container } = render_panel("copy")
    expect(headers(container)).toContain("Changed from Parent")
    expect(container.textContent).toContain("Same settings as parent.")
  })

  it("says changes can't be shown when the parent was deleted", () => {
    const { container } = render_panel("orphan")
    expect(container.textContent).toContain(
      "The parent run config was deleted, so changes can't be shown.",
    )
    expect(lineage_line(container)).toBe(
      "Derived from Deleted run config · No children",
    )
  })

  it("hides the changes section for a starting point", () => {
    const { container } = render_panel("root")
    expect(headers(container)).toEqual(["Run Configuration"])
    expect(lineage_line(container)).toBe("Starting point · 2 children")
  })

  it("shows only the lineage line for the deleted placeholder", () => {
    const { container } = render_panel("gone")
    expect(headers(container)).toEqual([])
    expect(container.textContent).toContain("Deleted run config")
    expect(lineage_line(container)).toBe(
      "This run config was deleted · 1 child",
    )
    expect(button_named(container, "Compare")).toBeNull()
    expect(button_named(container, "Compare to Parent")).toBeNull()
  })

  it("selects a parent from its link", async () => {
    const { container, select } = render_panel("merge")
    expect(lineage_line(container)).toBe(
      "Derived from Gusty Forest and Name copy · No children",
    )
    await fireEvent.click(button_named(container, "Name copy") as HTMLElement)
    expect(select).toHaveBeenCalledWith("copy")
    await fireEvent.click(
      button_named(container, "Gusty Forest") as HTMLElement,
    )
    expect(select).toHaveBeenLastCalledWith("child")
  })

  it("dispatches close from the close button", async () => {
    const { container, close } = render_panel("child")
    await fireEvent.click(
      container.querySelector('[aria-label="Close details"]') as HTMLElement,
    )
    expect(close).toHaveBeenCalledTimes(1)
  })

  it("opens Compare with this run config and an empty second column", async () => {
    const { container } = render_panel("child")
    await fireEvent.click(button_named(container, "Compare") as HTMLElement)
    expect(goto).toHaveBeenCalledWith(
      compare_run_configs_link(PROJECT_ID, TASK_ID, ["child", null]),
    )
  })

  it("opens Compare with the parent first and this run config second", async () => {
    const { container } = render_panel("child")
    await fireEvent.click(
      button_named(container, "Compare to Parent") as HTMLElement,
    )
    expect(goto).toHaveBeenCalledWith(
      compare_run_configs_link(PROJECT_ID, TASK_ID, ["root", "child"]),
    )
  })

  it("hides Compare to Parent without a live parent", () => {
    for (const id of ["orphan", "root"]) {
      const { container, unmount } = render_panel(id)
      expect(button_named(container, "Compare")).not.toBeNull()
      expect(button_named(container, "Compare to Parent")).toBeNull()
      unmount()
    }
  })

  it("shows the notes and who created the run config when there are notes", () => {
    const { container } = render_panel("child")
    expect(headers(container)).toContain("Notes")
    expect(container.textContent).toContain("Tried a kinder prompt.")
    expect(container.textContent).toContain("Created by an agent")
  })

  it("has no notes section without notes", () => {
    const { container } = render_panel("copy")
    expect(headers(container)).not.toContain("Notes")
  })

  it("lists the run config's properties", () => {
    const { container } = render_panel("child")
    expect(headers(container)).toContain("Run Configuration")
    expect(container.textContent).toContain("Created At")
    expect(container.textContent).toContain("Input Transformer")
  })
})
