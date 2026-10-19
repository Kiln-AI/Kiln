// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import KilnProBatchCountRow from "./kiln_pro_batch_count_row.svelte"

afterEach(cleanup)

function setup(props: Record<string, unknown> = {}) {
  const utils = render(KilnProBatchCountRow, {
    props: { label: "Sample Count", value: 20, ...props },
  })
  const count_input = utils.container.querySelector(
    'input[aria-label="Count"]',
  ) as HTMLInputElement
  return { ...utils, count_input }
}

// Svelte 4 keeps the live value of each prop in the instance context; this is
// what a parent's `bind:` reads back.
function bound_prop<T>(component: unknown, name: string): T {
  const instance = component as {
    $$: { ctx: unknown[]; props: Record<string, number> }
  }
  return instance.$$.ctx[instance.$$.props[name]] as T
}

describe("KilnProBatchCountRow", () => {
  it("renders the label and the stepper with the shipped layout", () => {
    const { container, count_input } = setup()
    const row = container.firstElementChild as HTMLElement
    expect(row.className).toBe("flex flex-row items-center gap-4")
    const label = row.firstElementChild as HTMLElement
    expect(label.className).toBe("flex-grow font-medium text-sm")
    expect(label.textContent).toBe("Sample Count")
    expect(count_input.value).toBe("20")
  })

  it("clamps to the bounds it is given", async () => {
    const { count_input } = setup({ value: 60, min: 35, max: 120 })
    await fireEvent.input(count_input, { target: { value: "9999" } })
    expect(count_input.value).toBe("120")
    // Below the minimum is left editable until the field settles.
    await fireEvent.input(count_input, { target: { value: "2" } })
    await fireEvent.blur(count_input)
    expect(count_input.value).toBe("35")
  })

  it("falls back to the stepper's own bounds when min and max are omitted", async () => {
    const { count_input } = setup()
    await fireEvent.input(count_input, { target: { value: "9999" } })
    expect(count_input.value).toBe("50")
    await fireEvent.input(count_input, { target: { value: "0" } })
    await fireEvent.blur(count_input)
    expect(count_input.value).toBe("1")
  })

  it("propagates stepper edits to the bound value", async () => {
    const { container, component } = setup({ max: 200 })
    const increase = container.querySelector(
      'button[aria-label="Increase"]',
    ) as HTMLButtonElement
    await fireEvent.click(increase)
    expect(bound_prop<number>(component, "value")).toBe(21)
  })
})
