// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, within } from "@testing-library/svelte"
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

vi.mock("$app/navigation", () => ({ goto: vi.fn() }))

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
  project_id: PROJECT_ID,
  task_id: TASK_ID,
  model_info: null,
  task_prompts: TASK_PROMPTS,
  project_tools: null,
}

// jsdom has no <dialog> methods.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true
  }
  HTMLDialogElement.prototype.close = function () {
    this.open = false
    this.dispatchEvent(new Event("close"))
  }
})

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
    properties: {
      prompt_id: "p_new",
      temperature: 0.7,
      tools_config: {
        tools: ["kiln_tool::web_search", "kiln_tool::sql_query"],
      },
    },
  })
}

// root ─┬─ child (prompt, tools, settings; has notes) ─┐
//       └─ copy ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┴─ merge, also from gone
// gone (deleted) ── orphan
function make_graph(): LineageGraph {
  return build_lineage_graph([
    make_dated_config("root", 0),
    child_config(),
    make_dated_config("copy", 2, ["root"]),
    make_dated_config("merge", 3, ["child", "copy", "gone"], {
      prompt_id: "p_new",
      temperature: 0.7,
      tools_config: {
        tools: ["kiln_tool::web_search", "kiln_tool::sql_query"],
      },
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
    props: { node, graph, ctx: CTX, available_tools: {} },
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

function lineage_line(container: HTMLElement): HTMLElement {
  return container.querySelector(
    '[data-testid="lineage-panel-line"]',
  ) as HTMLElement
}

function dialog_titled(container: HTMLElement, title: string) {
  const dialog = [...container.querySelectorAll("dialog")].find(
    (el) => el.querySelector("h3")?.textContent?.trim() === title,
  )
  if (!dialog) {
    throw new Error(`no dialog ${title}`)
  }
  return dialog
}

function list_texts(dialog: HTMLElement, label: string): string[] {
  const list = dialog.querySelector(`ul[aria-label="${label}"]`)
  return [...(list?.querySelectorAll("li") ?? [])].map(
    (li) => li.textContent?.trim() ?? "",
  )
}

afterEach(cleanup)

describe("LineagePanel", () => {
  it("shows the name, the lineage line and the creator badge in the header", () => {
    const { container } = render_panel("child")
    expect(container.textContent).toContain("Gusty Forest")
    expect(lineage_line(container).textContent?.trim()).toBe(
      "Derived from 1 parent · 1 child",
    )
    expect(container.querySelector(".badge")?.textContent?.trim()).toBe(
      "Agent Created",
    )
  })

  it("has no creator badge when no creator is recorded", () => {
    const { container } = render_panel("copy")
    expect(container.querySelector(".badge")).toBeNull()
  })

  it("puts the sections in order: notes, changes, run configuration", () => {
    const { container } = render_panel("child")
    expect(headers(container)).toEqual([
      "Notes",
      "Changed from Parent",
      "Run Configuration",
    ])
    expect(container.textContent).toContain("Tried a kinder prompt.")
  })

  it("shows each single change as the new value, linked, over the old one", () => {
    const { container } = render_panel("child")
    const rows = container.querySelector(
      '[data-testid="lineage-change-rows"]',
    ) as HTMLElement
    expect(rows.textContent).toContain("Prompt")
    const prompt = within(rows).getByText("Kinder Prompt")
    expect(prompt.closest("a")?.getAttribute("href")).toBe(
      "/prompts/p1/t1/saved/p_new",
    )
    const previous = [
      ...rows.querySelectorAll('[data-testid="lineage-change-previous"]'),
    ].map((el) => el.textContent?.replace(/\s+/g, " ").trim())
    expect(previous).toEqual(["was simple_prompt_builder", "was Temperature 1"])
  })

  it("summarizes a tools change and lists it in a dialog", async () => {
    const { container } = render_panel("child")
    const summary = button_named(container, "2 added") as HTMLButtonElement
    expect(summary).not.toBeNull()
    await fireEvent.click(summary)
    const dialog = dialog_titled(container, "Tools Changed")
    expect(dialog.open).toBe(true)
    expect(list_texts(dialog, "Added")).toEqual([
      "kiln_tool::web_search",
      "kiln_tool::sql_query",
    ])
    expect(dialog.querySelector('ul[aria-label="Removed"]')).toBeNull()
    expect(dialog.querySelector("li a")?.getAttribute("href")).toBe("/tools/p1")
  })

  it("returns focus to the summary when the tools dialog closes", async () => {
    const { container } = render_panel("child")
    const summary = button_named(container, "2 added") as HTMLButtonElement
    await fireEvent.click(summary)
    dialog_titled(container, "Tools Changed").close()
    expect(document.activeElement).toBe(summary)
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
    expect(lineage_line(container).textContent?.trim()).toBe(
      "Derived from 1 parent",
    )
  })

  it("hides the changes and notes sections for a starting point", () => {
    const { container } = render_panel("root")
    expect(headers(container)).toEqual(["Run Configuration"])
    expect(lineage_line(container).textContent?.trim()).toBe(
      "Starting point · 2 children",
    )
  })

  it("shows only the header for the deleted placeholder", () => {
    const { container } = render_panel("gone")
    expect(headers(container)).toEqual([])
    expect(container.textContent).toContain("Deleted run config")
    expect(lineage_line(container).textContent?.trim()).toBe(
      "This run config was deleted · 2 children",
    )
    expect(container.querySelector("a.link")).toBeNull()
  })

  it("lists parents and children in a dialog from the lineage line", async () => {
    const { container } = render_panel("merge")
    expect(lineage_line(container).textContent?.trim()).toBe(
      "Derived from 3 parents",
    )
    await fireEvent.click(lineage_line(container))
    const dialog = dialog_titled(container, "Lineage")
    expect(dialog.open).toBe(true)
    expect(list_texts(dialog, "Parents")).toEqual([
      "Gusty Forest",
      "Name copy",
      "Deleted run config",
    ])
    expect(dialog.querySelector('ul[aria-label="Children"]')).toBeNull()
    expect(button_named(dialog, "Deleted run config")).toBeNull()
  })

  it("selects a relative from the dialog and closes it", async () => {
    const { container, select } = render_panel("merge")
    await fireEvent.click(lineage_line(container))
    const dialog = dialog_titled(container, "Lineage")
    await fireEvent.click(button_named(dialog, "Name copy") as HTMLElement)
    expect(select).toHaveBeenCalledWith("copy")
    expect(dialog.open).toBe(false)
    expect(document.activeElement).toBe(lineage_line(container))
  })

  it("shows the lineage line as plain text with no parents or children", () => {
    const graph = build_lineage_graph([make_dated_config("alone", 0)])
    const node = graph.nodes.get("alone")
    if (!node) {
      throw new Error("no node alone")
    }
    const { container } = render(LineagePanel, {
      props: { node, graph, ctx: CTX, available_tools: {} },
    })
    const line = lineage_line(container)
    expect(line.tagName).toBe("DIV")
    expect(line.textContent?.trim()).toBe("No recorded parent")
  })

  it("dispatches close from the close button", async () => {
    const { container, close } = render_panel("child")
    await fireEvent.click(
      container.querySelector('[aria-label="Close details"]') as HTMLElement,
    )
    expect(close).toHaveBeenCalledTimes(1)
  })

  it("links to Compare with this run config and an empty second column", () => {
    const { container } = render_panel("child")
    const link = within(container).getByText("Compare eval results to others")
    expect(link.getAttribute("href")).toBe(
      compare_run_configs_link(PROJECT_ID, TASK_ID, ["child", null]),
    )
    expect(button_named(container, "Compare to Parent")).toBeNull()
  })

  it("lists the run config's properties", () => {
    const { container } = render_panel("child")
    expect(container.textContent).toContain("Created At")
    expect(container.textContent).toContain("Input Transformer")
  })
})
