// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import BadgeList from "./badge_list.svelte"

// jsdom does not implement HTMLDialogElement.showModal/close. The "+N more"
// modal relies on them, so polyfill with no-ops that track the open state.
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

describe("BadgeList", () => {
  it("renders a plain string as-is", () => {
    const { container } = render(BadgeList, { props: { items: "None" } })
    expect(container.textContent?.trim()).toBe("None")
  })

  it("renders all badges by default (no collapse)", () => {
    const { container } = render(BadgeList, {
      props: { items: ["alpha", "beta", "gamma"] },
    })
    expect(container.textContent).toContain("alpha")
    expect(container.textContent).toContain("beta")
    expect(container.textContent).toContain("gamma")
    expect(container.textContent).not.toContain("more")
  })

  it("collapses to the first badge plus a '+N more' badge", () => {
    const { container } = render(BadgeList, {
      props: { items: ["alpha", "beta", "gamma"], collapse: true },
    })
    // The inline row (distinguished by `items-center`) shows only the first
    // item plus the "+N more" badge; the rest live in the (hidden) modal.
    const inline = container.querySelector(".items-center")
    expect(inline?.textContent).toContain("alpha")
    expect(inline?.textContent).toContain("+2 more")
    expect(inline?.textContent).not.toContain("beta")
    expect(inline?.textContent).not.toContain("gamma")
  })

  it("does not collapse a single item", () => {
    const { container } = render(BadgeList, {
      props: { items: ["alpha"], collapse: true },
    })
    expect(container.textContent).toContain("alpha")
    expect(container.textContent).not.toContain("more")
  })

  it("opens a titled modal with the full list when '+N more' is clicked", async () => {
    const { container, getByText } = render(BadgeList, {
      props: {
        items: ["alpha", "beta", "gamma"],
        links: ["/t/a", "/t/b", "/t/c"],
        collapse: true,
        modal_title: "Available Tools",
      },
    })
    await fireEvent.click(getByText("+2 more"))
    const dialog = container.querySelector("dialog")
    expect(dialog?.textContent).toContain("Available Tools")
    expect(dialog?.textContent).toContain("beta")
    expect(dialog?.textContent).toContain("gamma")
    // Links render as anchors in the modal.
    const anchors = dialog?.querySelectorAll("a.badge")
    expect(anchors?.length).toBe(3)
    expect(anchors?.[2].getAttribute("href")).toBe("/t/c")
  })
})
