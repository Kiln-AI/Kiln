// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import KilnProBatchPlan from "./kiln_pro_batch_plan.svelte"

const PLAN = {
  prompts: ["first prompt", "second prompt"],
  summary: "A two line plan.",
}

afterEach(cleanup)

function setup(props: Record<string, unknown> = {}) {
  return render(KilnProBatchPlan, {
    props: {
      plan: PLAN,
      on_generate_inputs: () => {},
      on_regenerate: () => {},
      on_delete_prompt: () => {},
      ...props,
    },
  })
}

// The prompts table's toggle is the only button carrying an aria-label.
function prompts_toggle(container: HTMLElement): HTMLButtonElement {
  return container.querySelector(
    "button[aria-label]",
  ) as unknown as HTMLButtonElement
}

function header_text(container: HTMLElement): string {
  return (
    container.querySelector("span.text-sm.font-medium")?.textContent?.trim() ??
    ""
  )
}

function description_text(container: HTMLElement): string | null {
  const node = container.querySelector(
    "div.flex.flex-col.gap-2 > div.text-sm.text-gray-500",
  )
  return node ? node.textContent?.trim() ?? "" : null
}

// The rows table only mounts once the prompts toggle is expanded.
function column_header_text(container: HTMLElement): string {
  return container.querySelector("thead th")?.textContent?.trim() ?? ""
}

describe("prompts table pass-throughs", () => {
  it("leaves the /generate strings untouched by default", async () => {
    const { container } = setup()
    expect(header_text(container)).toBe("All Dataset Items (2)")
    expect(prompts_toggle(container).getAttribute("aria-label")).toBe(
      "Show dataset items",
    )
    await fireEvent.click(prompts_toggle(container))
    expect(description_text(container)).toBe(
      "Each prompt below will be used to guide one dataset sample.",
    )
    // /generate's rows really are generation prompts, and it overrides
    // nothing — so the default column header is the one that flow ships.
    expect(column_header_text(container)).toBe("Prompt")
  })

  it("passes column_label down to the rows table's header", async () => {
    // The eval builder reaches the rows table only through this component, so
    // the override has to survive the hop.
    const { container } = setup({ column_label: "Item Guidance" })
    await fireEvent.click(prompts_toggle(container))
    expect(column_header_text(container)).toBe("Item Guidance")
  })

  it("passes items_label down to the header and the aria-label", () => {
    const { container } = setup({ items_label: "Items" })
    expect(header_text(container)).toBe("All Items (2)")
    expect(prompts_toggle(container).getAttribute("aria-label")).toBe(
      "Show items",
    )
  })

  it("passes expanded_description down, including false", async () => {
    const { container } = setup({ expanded_description: false })
    await fireEvent.click(prompts_toggle(container))
    expect(description_text(container)).toBeNull()

    cleanup()
    const custom = setup({ expanded_description: "One line per run." })
    await fireEvent.click(prompts_toggle(custom.container))
    expect(description_text(custom.container)).toBe("One line per run.")
  })
})

describe("shared defaults", () => {
  // Both surfaces render these: /generate passes no override, and the eval
  // builder deliberately relies on the same defaults. Changing either string
  // changes both flows at once, so it is pinned here rather than left to a
  // caller's assertion.
  it("labels the regenerate button and the summary panel", () => {
    const { container } = setup()
    const buttons = Array.from(container.querySelectorAll("button")).map((b) =>
      b.textContent?.trim(),
    )
    expect(buttons).toContain("Refine Plan")
    expect(container.textContent).toContain("Overview")
    expect(container.textContent).not.toContain("Batch Overview")
  })
})
