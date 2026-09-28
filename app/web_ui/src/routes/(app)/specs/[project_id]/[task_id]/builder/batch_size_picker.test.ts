// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import BatchSizePicker from "./batch_size_picker.svelte"
import { CUSTOM_MAX, CUSTOM_MIN, type BatchSize } from "./batch_profiles"

afterEach(() => {
  cleanup()
})

function size(profile: BatchSize["profile"]): BatchSize {
  return { profile, custom_count: 60 }
}

describe("BatchSizePicker", () => {
  it("shows the profile alone on a preset", () => {
    // The presets name their own count, so a stepper beside them would offer
    // to contradict the option the user just picked.
    const { container, queryByText } = render(BatchSizePicker, {
      props: { size: size("standard") },
    })
    expect(queryByText("Item Count")).toBeNull()
    expect(container.querySelector('input[aria-label="Count"]')).toBeNull()
  })

  it("adds the Item Count row, bounded, on Custom", async () => {
    const { container, queryByText } = render(BatchSizePicker, {
      props: { size: size("custom") },
    })
    expect(queryByText("Item Count")).not.toBeNull()

    const stepper = container.querySelector<HTMLInputElement>(
      'input[aria-label="Count"]',
    )
    if (!stepper) throw new Error("no Item Count stepper")
    await fireEvent.input(stepper, { target: { value: "9999" } })
    expect(stepper.value).toBe(String(CUSTOM_MAX))
    // Below the floor is left editable until blur, which settles it.
    await fireEvent.input(stepper, { target: { value: "1" } })
    await fireEvent.blur(stepper)
    expect(stepper.value).toBe(String(CUSTOM_MIN))
  })
})
