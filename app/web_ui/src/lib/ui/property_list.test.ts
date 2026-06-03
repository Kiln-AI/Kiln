// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import PropertyList from "./property_list.svelte"
import type { UiProperty } from "./property_list"

// jsdom does not implement HTMLDialogElement.showModal/close. The Dialog
// component used for the "+N more" modal calls them, so polyfill with no-ops
// that just track the open state.
beforeAll(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () {
      this.open = true
    }
  }
  if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function () {
      this.open = false
    }
  }
})

afterEach(() => {
  cleanup()
})

function render_props(properties: UiProperty[]) {
  return render(PropertyList, { props: { properties } })
}

describe("PropertyList collapse_badges", () => {
  it("renders all badges when collapse_badges is not set", () => {
    const { container } = render_props([
      {
        name: "Available Tools",
        value: ["alpha", "beta", "gamma"],
        badge: true,
      },
    ])
    expect(container.textContent).toContain("alpha")
    expect(container.textContent).toContain("beta")
    expect(container.textContent).toContain("gamma")
    expect(container.textContent).not.toContain("more")
  })

  it("collapses to first badge plus a '+N more' badge", () => {
    const { container } = render_props([
      {
        name: "Available Tools",
        value: ["alpha", "beta", "gamma"],
        badge: true,
        collapse_badges: true,
      },
    ])
    // First badge shown inline, the rest hidden until the modal is opened.
    expect(container.textContent).toContain("alpha")
    expect(container.textContent).toContain("+2 more")
    expect(container.textContent).not.toContain("beta")
    expect(container.textContent).not.toContain("gamma")
  })

  it("does not collapse when there is only one value", () => {
    const { container } = render_props([
      {
        name: "Available Tools",
        value: ["alpha"],
        badge: true,
        collapse_badges: true,
      },
    ])
    expect(container.textContent).toContain("alpha")
    expect(container.textContent).not.toContain("more")
  })

  it("opens a modal listing the full set when '+N more' is clicked", async () => {
    const { container, getByText } = render_props([
      {
        name: "Available Tools",
        value: ["alpha", "beta", "gamma"],
        badge: true,
        collapse_badges: true,
      },
    ])
    await fireEvent.click(getByText("+2 more"))
    // The wide modal renders the full list (including the collapsed values).
    expect(container.textContent).toContain("beta")
    expect(container.textContent).toContain("gamma")
    // Modal is titled by the property name.
    expect(container.querySelector("dialog")?.textContent).toContain(
      "Available Tools",
    )
  })

  it("renders the same badge pills (semantic links) in the modal", async () => {
    const { getByText, container } = render_props([
      {
        name: "Available Tools",
        value: ["alpha", "beta"],
        links: ["/tools/a", "/tools/b"],
        badge: true,
        collapse_badges: true,
      },
    ])
    await fireEvent.click(getByText("+1 more"))
    // Modal pills use the same badge markup as the inline list: semantic
    // anchors for links pointing at the tool's page.
    const pills = container.querySelectorAll("dialog a.badge.badge-outline")
    expect(pills.length).toBe(2)
    expect(pills[1].textContent?.trim()).toBe("beta")
    expect(pills[1].getAttribute("href")).toBe("/tools/b")
  })
})
