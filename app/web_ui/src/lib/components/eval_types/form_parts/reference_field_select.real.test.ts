// @vitest-environment jsdom
//
// This test renders the REAL FormElement → FancySelect (no stubs) so it
// validates the actual DOM the user sees. The stubbed tests in
// form_parts.test.ts cover the component API; THIS test is the source of
// truth for the text-to-dropdown transition bug.

import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

// Mock only $app/navigation (FancySelect imports `goto` for empty_state_link)
vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
}))

// DO NOT mock FormElement or Dialog — we want real components.

const ReferenceFieldSelect = (await import("./reference_field_select.svelte"))
  .default

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-extraneous-class
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(
      globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }
    ).ResizeObserver = ResizeObserverStub
  }
})

/** Read the closed-state selected label from the real FancySelect DOM. */
function readSelectedLabel(container: HTMLElement): string {
  const listbox = container.querySelector('[role="listbox"]')
  const span = listbox?.querySelector("span.truncate")
  return span?.textContent?.trim() ?? "(not found)"
}

describe("ReferenceFieldSelect – real FancySelect (no stubs)", () => {
  it("text-to-dropdown transition preserves typed value in real FancySelect DOM", async () => {
    // 1. Render with no candidates → plain text input
    const { container, component } = render(ReferenceFieldSelect, {
      props: { id_prefix: "t", value: null, candidate_keys: [] },
    })

    // Confirm we're in text-input mode (no listbox)
    expect(container.querySelector('[role="listbox"]')).toBeNull()

    // Find the real <input> rendered by FormElement (id="t_reference_key")
    const input = container.querySelector(
      "#t_reference_key",
    ) as HTMLInputElement
    expect(input).toBeTruthy()
    expect(input.tagName).toBe("INPUT")

    // 2. Type "asdf" via fireEvent.input
    await fireEvent.input(input, { target: { value: "asdf" } })
    await tick()

    // Confirm value propagated
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("asdf")

    // 3. candidate_keys becomes non-empty → dropdown appears
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({ candidate_keys: ["foo"] })
    await tick()
    await tick()

    // 4. Assert the REAL fancy_select DOM
    const label = readSelectedLabel(container)

    // The label MUST be "asdf", NOT "Select an option" (the empty_label placeholder).
    expect(label).toBe("asdf")

    // Also verify the component's exported value
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("asdf")
  })

  it("initial value shows correctly in dropdown mode", async () => {
    const { container, component } = render(ReferenceFieldSelect, {
      props: {
        id_prefix: "t",
        value: "expected_answer",
        candidate_keys: ["expected_answer", "expected_status"],
      },
    })
    await tick()

    const label = readSelectedLabel(container)
    expect(label).toBe("expected_answer")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("expected_answer")
  })

  it("non-candidate initial value shows in dropdown (added to options)", async () => {
    const { container, component } = render(ReferenceFieldSelect, {
      props: {
        id_prefix: "t",
        value: "custom_field",
        candidate_keys: ["expected_answer"],
      },
    })
    await tick()

    const label = readSelectedLabel(container)
    expect(label).toBe("custom_field")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("custom_field")
  })

  it("null value in dropdown mode shows empty placeholder, not Custom sentinel", async () => {
    const { container, component } = render(ReferenceFieldSelect, {
      props: { id_prefix: "t", value: null, candidate_keys: ["foo"] },
    })
    await tick()

    // When value is null, the dropdown should show the empty placeholder
    // ("Select an option"), NOT "Custom Field Name". The Custom sentinel
    // is only a momentary trigger for the modal, never a persisted selection.
    const label = readSelectedLabel(container)
    expect(label).toBe("Select an option")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBeNull()
  })

  it("selecting Custom Field Name does not persist as selected label", async () => {
    const { container, component } = render(ReferenceFieldSelect, {
      props: {
        id_prefix: "t",
        value: "foo",
        candidate_keys: ["foo", "bar"],
      },
    })
    await tick()

    // Confirm initial state: "foo" is selected
    expect(readSelectedLabel(container)).toBe("foo")

    // Click the Custom Field Name option
    const listbox = container.querySelector('[role="listbox"]')
    await fireEvent.click(listbox!)
    await tick()

    // Find and click the Custom sentinel option in the dropdown
    const customOption = container.querySelector(
      'button[data-value="__custom__"]',
    )
    if (customOption) {
      await fireEvent.click(customOption)
      await tick()
    }

    // The dropdown should revert to the prior selection ("foo"), not
    // show "Custom Field Name" as a persisted label.
    const labelAfterCustomClick = readSelectedLabel(container)
    expect(labelAfterCustomClick).not.toBe("Custom Field Name")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("foo")
  })

  it("typed value matching a future candidate selects it correctly", async () => {
    const { container, component } = render(ReferenceFieldSelect, {
      props: { id_prefix: "t", value: null, candidate_keys: [] },
    })

    const input = container.querySelector(
      "#t_reference_key",
    ) as HTMLInputElement
    await fireEvent.input(input, { target: { value: "expected_answer" } })
    await tick()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({
      candidate_keys: ["expected_answer", "expected_status"],
    })
    await tick()
    await tick()

    const label = readSelectedLabel(container)
    expect(label).toBe("expected_answer")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("expected_answer")
  })

  it("pre-populated value in text mode is preserved on transition", async () => {
    const { container, component } = render(ReferenceFieldSelect, {
      props: { id_prefix: "t", value: "my_field", candidate_keys: [] },
    })
    await tick()

    // Confirm text mode and value
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("my_field")

    // Transition to dropdown
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({ candidate_keys: ["foo", "bar"] })
    await tick()
    await tick()

    const label = readSelectedLabel(container)
    expect(label).toBe("my_field")
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("my_field")
  })
})
