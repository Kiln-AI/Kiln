// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach, vi } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import FilterTagsDialog from "./filter_tags_dialog.svelte"

// jsdom does not implement HTMLDialogElement.showModal/close.
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

const available = {
  golden: 12,
  needs_rating: 3,
  eval_set: 7,
}

describe("FilterTagsDialog tag search", () => {
  it("renders all available tags by default, sorted by count", () => {
    const { container } = render(FilterTagsDialog, {
      props: { title: "Filter by Tags", available_filter_tags: available },
    })
    const tags = [...container.querySelectorAll("button.badge")].map((b) =>
      b.textContent?.trim(),
    )
    expect(tags).toEqual(["golden (12)", "eval_set (7)", "needs_rating (3)"])
  })

  it("filters the available tags by case-insensitive substring as the user types", async () => {
    const { container, getByPlaceholderText } = render(FilterTagsDialog, {
      props: { title: "Filter by Tags", available_filter_tags: available },
    })
    const input = getByPlaceholderText("Search tags…")
    await fireEvent.input(input, { target: { value: "EVAL" } })

    const tags = [...container.querySelectorAll("button.badge")].map((b) =>
      b.textContent?.trim(),
    )
    expect(tags).toEqual(["eval_set (7)"])
  })

  it("shows a no-results message when nothing matches", async () => {
    const { container, getByPlaceholderText } = render(FilterTagsDialog, {
      props: { title: "Filter by Tags", available_filter_tags: available },
    })
    await fireEvent.input(getByPlaceholderText("Search tags…"), {
      target: { value: "zzz" },
    })
    expect(container.querySelectorAll("button.badge").length).toBe(0)
    expect(container.textContent).toContain('No tags match "zzz".')
  })

  it("calls onAddFilterTag when a tag is clicked", async () => {
    const onAddFilterTag = vi.fn()
    const { getByText } = render(FilterTagsDialog, {
      props: {
        title: "Filter by Tags",
        available_filter_tags: available,
        onAddFilterTag,
      },
    })
    await fireEvent.click(getByText("golden (12)"))
    expect(onAddFilterTag).toHaveBeenCalledWith("golden")
  })

  it("does not show the search input when there are no available tags", () => {
    const { queryByPlaceholderText, container } = render(FilterTagsDialog, {
      props: { title: "Filter by Tags", available_filter_tags: {} },
    })
    expect(queryByPlaceholderText("Search tags…")).toBeNull()
    expect(container.textContent).toContain(
      "Any further filters would show zero results.",
    )
  })

  it("resets the search text when the dialog is re-opened", async () => {
    const { getByPlaceholderText, component } = render(FilterTagsDialog, {
      props: { title: "Filter by Tags", available_filter_tags: available },
    })
    const input = getByPlaceholderText("Search tags…") as HTMLInputElement
    await fireEvent.input(input, { target: { value: "golden" } })
    expect(input.value).toBe("golden")

    component.show()
    await Promise.resolve()
    expect(input.value).toBe("")
  })
})
