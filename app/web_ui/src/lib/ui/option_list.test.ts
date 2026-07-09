// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import OptionList from "./option_list.svelte"
import type { OptionListItem } from "./option_list_types"

afterEach(() => {
  cleanup()
})

const base_options: OptionListItem[] = [
  { id: "a", name: "Option A", description: "First option." },
  { id: "b", name: "Option B", description: "Second option." },
]

describe("OptionList", () => {
  it("renders every option's name and description", () => {
    const { container } = render(OptionList, {
      props: { options: base_options, select_option: () => {} },
    })
    expect(container.textContent).toContain("Option A")
    expect(container.textContent).toContain("First option.")
    expect(container.textContent).toContain("Option B")
    expect(container.textContent).toContain("Second option.")
    // One button per option.
    expect(container.querySelectorAll("button").length).toBe(2)
  })

  it("calls select_option with the option id on click", async () => {
    const select_option = vi.fn()
    const { getByText } = render(OptionList, {
      props: { options: base_options, select_option },
    })
    await fireEvent.click(getByText("Option B"))
    expect(select_option).toHaveBeenCalledTimes(1)
    expect(select_option).toHaveBeenCalledWith("b")
  })

  it("shows a Recommended badge only on recommended options", () => {
    const { container } = render(OptionList, {
      props: {
        options: [{ ...base_options[0], recommended: true }, base_options[1]],
        select_option: () => {},
      },
    })
    const badges = container.querySelectorAll(".badge")
    expect(badges.length).toBe(1)
    expect(badges[0].textContent).toContain("Recommended")
  })

  it("renders tag badges from the tags array", () => {
    const { container } = render(OptionList, {
      props: {
        options: [
          { ...base_options[0], tags: [{ label: "Beta", tone: "beta" }] },
        ],
        select_option: () => {},
      },
    })
    const badge = container.querySelector(".badge")
    expect(badge?.textContent?.trim()).toBe("Beta")
    expect(badge?.classList.contains("badge-primary")).toBe(true)
  })

  it("does not render an icon square when no icon is provided", () => {
    const { container } = render(OptionList, {
      props: { options: base_options, select_option: () => {} },
    })
    expect(container.querySelector(".option-icon")).toBeNull()
  })

  it("disables the button for disabled options", () => {
    // The browser blocks clicks on disabled buttons natively, so we assert the
    // disabled attribute rather than click behavior (jsdom still dispatches
    // events to disabled elements).
    const { getByText } = render(OptionList, {
      props: {
        options: [{ ...base_options[0], disabled: true }],
        select_option: () => {},
      },
    })
    const button = getByText("Option A").closest("button")
    expect(button?.disabled).toBe(true)
  })
})
