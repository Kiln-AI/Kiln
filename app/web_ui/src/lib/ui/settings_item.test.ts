// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import SettingsItem from "./settings_item.svelte"

vi.mock("$app/navigation", () => ({ goto: vi.fn() }))

afterEach(() => cleanup())

const BASE = {
  name: "OpenEnv",
  description: "Connect an OpenEnv server.",
  button_text: "Connect",
}

describe("settings_item without a link", () => {
  it("is a button with the description as plain text", async () => {
    const on_click = vi.fn()
    const { container } = render(SettingsItem, {
      props: { ...BASE, on_click },
    })
    const row = container.firstElementChild as HTMLElement
    expect(row.tagName).toBe("BUTTON")
    expect(row.getAttribute("role")).toBeNull()
    expect(container.querySelector("a")).toBeNull()
    expect(container.querySelector("p")!.textContent!.trim()).toBe(
      "Connect an OpenEnv server.",
    )
    await fireEvent.click(row)
    expect(on_click).toHaveBeenCalledOnce()
  })

  it("ignores a link label without an href", () => {
    const { container } = render(SettingsItem, {
      props: { ...BASE, link_label: "Learn more" },
    })
    expect(container.firstElementChild!.tagName).toBe("BUTTON")
    expect(container.querySelector("a")).toBeNull()
  })
})

describe("settings_item with a link", () => {
  function render_with_link(on_click = vi.fn()) {
    const result = render(SettingsItem, {
      props: {
        ...BASE,
        on_click,
        link_label: "Learn more",
        link_href: "https://docs.kiln.tech/docs/tools-and-mcp",
      },
    })
    return { ...result, on_click }
  }

  it("ends the description with a link that opens in a new tab", () => {
    const { container } = render_with_link()
    const link = container.querySelector("p a") as HTMLAnchorElement
    expect(link.textContent).toBe("Learn more")
    expect(link.getAttribute("href")).toBe(
      "https://docs.kiln.tech/docs/tools-and-mcp",
    )
    expect(link.getAttribute("target")).toBe("_blank")
    expect(link.getAttribute("rel")).toBe("noopener noreferrer")
  })

  it("is a focusable div with the button role, so the link isn't inside a button", () => {
    const { container } = render_with_link()
    const row = container.firstElementChild as HTMLElement
    expect(row.tagName).toBe("DIV")
    expect(row.getAttribute("role")).toBe("button")
    expect(row.getAttribute("tabindex")).toBe("0")
    expect(container.querySelector("button")).toBeNull()
  })

  it("runs the row action on click, Enter and Space", async () => {
    const { container, on_click } = render_with_link()
    const row = container.firstElementChild as HTMLElement
    await fireEvent.click(row)
    await fireEvent.keyDown(row, { key: "Enter" })
    await fireEvent.keyDown(row, { key: " " })
    expect(on_click).toHaveBeenCalledTimes(3)
  })

  it("doesn't run the row action when the link is clicked", async () => {
    const { container, on_click } = render_with_link()
    const link = container.querySelector("a")!
    link.addEventListener("click", (e) => e.preventDefault())
    await fireEvent.click(link)
    await fireEvent.keyDown(link, { key: "Enter" })
    expect(on_click).not.toHaveBeenCalled()
  })
})
