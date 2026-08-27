// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import KilnProBatchForm from "./kiln_pro_batch_form.svelte"

const GUIDANCE_DESCRIPTION = `This allows you to control the dataset you are generating. For example, "10% of the dataset should be in Spanish."`

afterEach(cleanup)

function setup(props: Record<string, unknown> = {}) {
  const utils = render(KilnProBatchForm, {
    props: { count: 50, guidance: "", ...props },
  })
  const count_input = utils.container.querySelector(
    'input[aria-label="Count"]',
  ) as HTMLInputElement
  const guidance_box = utils.container.querySelector(
    "textarea",
  ) as HTMLTextAreaElement
  return { ...utils, count_input, guidance_box }
}

function reset_button(container: HTMLElement): HTMLButtonElement | null {
  return (
    Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent?.trim() === "Reset",
    ) ?? null
  )
}

// Svelte 4 keeps the live value of each prop in the instance context; this is
// what a parent's `bind:` reads back. Lets the tests check outward flow
// without a wrapper component.
function bound_prop<T>(component: unknown, name: string): T {
  const instance = component as {
    $$: { ctx: unknown[]; props: Record<string, number> }
  }
  return instance.$$.ctx[instance.$$.props[name]] as T
}

describe("KilnProBatchForm", () => {
  it("renders the count row with the shipped layout and label", () => {
    const { container, count_input } = setup()
    const row = container.firstElementChild as HTMLElement
    expect(row.className).toBe("flex flex-row items-center gap-4")
    const label = row.firstElementChild as HTMLElement
    expect(label.className).toBe("flex-grow font-medium text-sm")
    expect(label.textContent).toBe("Sample Count")
    expect(count_input).not.toBeNull()
    expect(count_input.value).toBe("50")
  })

  it("caps the count at 200 by default", async () => {
    const { count_input } = setup()
    await fireEvent.input(count_input, { target: { value: "9999" } })
    expect(count_input.value).toBe("200")
  })

  it("honours a count_max override", async () => {
    const { count_input } = setup({ count_max: 20 })
    await fireEvent.input(count_input, { target: { value: "9999" } })
    expect(count_input.value).toBe("20")
  })

  it("renders the guidance field with the shipped label and description", () => {
    const { container, guidance_box } = setup()
    expect(guidance_box).not.toBeNull()
    expect(guidance_box.getAttribute("aria-label")).toBe("Guidance")
    expect(container.textContent).toContain(GUIDANCE_DESCRIPTION)
    // The id the generate page's label and autofill hooks rely on, and the
    // extra-large box height the shipped page renders.
    expect(guidance_box.id).toBe("batch_guidance")
    expect(guidance_box.className).toContain("h-96")
  })

  it("uses a guidance_id override for the field's id", () => {
    const { guidance_box } = setup({ guidance_id: "eval_batch_guidance" })
    expect(guidance_box.id).toBe("eval_batch_guidance")
  })

  it("uses count_label as the noun in the count row", () => {
    const { container } = setup({ count_label: "Trace Count" })
    const label = container.firstElementChild?.firstElementChild as HTMLElement
    expect(label.textContent).toBe("Trace Count")
  })

  it("hides Reset when there is no guidance template", () => {
    const { container } = setup({ guidance: "edited by hand" })
    expect(reset_button(container)).toBeNull()
  })

  it("hides Reset when the guidance still matches the template", () => {
    const { container } = setup({
      guidance: "start here",
      guidance_template: "start here",
    })
    expect(reset_button(container)).toBeNull()
  })

  it("shows Reset once guidance differs from the template, and restores it", async () => {
    const { container, guidance_box } = setup({
      guidance: "edited",
      guidance_template: "start here",
    })
    const reset = reset_button(container)
    expect(reset).not.toBeNull()
    await fireEvent.click(reset as HTMLButtonElement)
    expect(guidance_box.value).toBe("start here")
    // Back on the template, so the action disappears again.
    expect(reset_button(container)).toBeNull()
  })

  it("renders no warning by default", () => {
    const { container } = setup()
    expect(container.querySelector("svg.text-warning")).toBeNull()
  })

  it("renders a tight amber warning after the rows when warning_message is set", () => {
    const { container } = setup({ warning_message: "This costs money." })
    const warning = container.lastElementChild as HTMLElement
    expect(warning.textContent).toContain("This costs money.")
    // Amber, and tight so it sits flush above the caller's submit button.
    expect(warning.querySelector("svg.text-warning")).not.toBeNull()
    expect(warning.className).not.toContain("mt-2")
    expect((warning.lastElementChild as HTMLElement).className).toContain(
      "pl-1",
    )
  })

  it("propagates count and guidance edits to the bound props", async () => {
    const { container, component, guidance_box } = setup()
    const increase = container.querySelector(
      'button[aria-label="Increase"]',
    ) as HTMLButtonElement
    await fireEvent.click(increase)
    expect(bound_prop<number>(component, "count")).toBe(51)

    await fireEvent.input(guidance_box, { target: { value: "be terse" } })
    expect(bound_prop<string>(component, "guidance")).toBe("be terse")
  })
})
