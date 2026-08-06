// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import IncrementUi from "./increment_ui.svelte"

function setup(props: { value: number; min?: number; max?: number }) {
  const utils = render(IncrementUi, { props })
  const input = utils.container.querySelector(
    'input[aria-label="Count"]',
  ) as HTMLInputElement
  const dec = utils.container.querySelector(
    'button[aria-label="Decrease"]',
  ) as HTMLButtonElement
  const inc = utils.container.querySelector(
    'button[aria-label="Increase"]',
  ) as HTMLButtonElement
  return { ...utils, input, dec, inc }
}

describe("IncrementUi", () => {
  it("shows the current value in a typable input", () => {
    const { input } = setup({ value: 50, max: 500 })
    expect(input).not.toBeNull()
    expect(input.value).toBe("50")
  })

  it("commits a typed value on blur", async () => {
    const { input } = setup({ value: 50, max: 500 })
    await fireEvent.input(input, { target: { value: "123" } })
    await fireEvent.blur(input)
    expect(input.value).toBe("123")
  })

  it("clamps above max immediately while typing, not on blur", async () => {
    const { input } = setup({ value: 50, max: 500 })
    await fireEvent.input(input, { target: { value: "9999" } })
    // Clamped straight away — no blur needed.
    expect(input.value).toBe("500")
  })

  it("strips non-digits as they are typed or pasted", async () => {
    const { input } = setup({ value: 50, max: 500 })
    await fireEvent.input(input, { target: { value: "12abc" } })
    expect(input.value).toBe("12")
    await fireEvent.input(input, { target: { value: "abc" } })
    expect(input.value).toBe("")
    // An all-letters entry leaves the box empty and editable; blur settles it.
    await fireEvent.blur(input)
    expect(input.value).toBe("1")
  })

  it("lets the box be cleared mid-edit so it stays editable", async () => {
    const { input } = setup({ value: 50, min: 1, max: 500 })
    await fireEvent.input(input, { target: { value: "" } })
    // Not snapped to min while typing.
    expect(input.value).toBe("")
    await fireEvent.input(input, { target: { value: "7" } })
    expect(input.value).toBe("7")
  })

  it("clamps a typed value below min up to min", async () => {
    const { input } = setup({ value: 50, min: 1, max: 500 })
    await fireEvent.input(input, { target: { value: "0" } })
    await fireEvent.blur(input)
    expect(input.value).toBe("1")
  })

  it("falls back to min for a blank or unparseable entry", async () => {
    const { input } = setup({ value: 50, min: 1, max: 500 })
    await fireEvent.input(input, { target: { value: "" } })
    await fireEvent.blur(input)
    expect(input.value).toBe("1")
  })

  it("commits on Enter without submitting the form", async () => {
    const { input } = setup({ value: 50, max: 500 })
    await fireEvent.input(input, { target: { value: "77" } })
    await fireEvent.keyDown(input, { key: "Enter" })
    expect(input.value).toBe("77")
  })

  it("steps within bounds and clamps at the edges", async () => {
    const { input, inc, dec } = setup({ value: 499, min: 1, max: 500 })
    await fireEvent.click(inc)
    expect(input.value).toBe("500")
    // Already at max — stays put.
    await fireEvent.click(inc)
    expect(input.value).toBe("500")
    await fireEvent.click(dec)
    expect(input.value).toBe("499")
  })

  it("uses type=button so the steppers don't submit an enclosing form", () => {
    const { inc, dec } = setup({ value: 5 })
    expect(inc.type).toBe("button")
    expect(dec.type).toBe("button")
  })
})
