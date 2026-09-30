// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import TagInput from "./tag_input.svelte"

afterEach(() => {
  cleanup()
})

describe("TagInput", () => {
  it("renders initial tags as badges", () => {
    const { container } = render(TagInput, {
      props: { tags: ["apple", "banana"], id: "test" },
    })
    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    expect(tagContainer.textContent).toContain("apple")
    expect(tagContainer.textContent).toContain("banana")
  })

  it("renders empty state with just an input", () => {
    const { container } = render(TagInput, {
      props: { tags: [], id: "test" },
    })
    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    const badges = tagContainer.querySelectorAll(".badge")
    expect(badges).toHaveLength(0)
    const input = tagContainer.querySelector("input[type='text']")
    expect(input).toBeTruthy()
  })

  it("adds a tag on Enter", async () => {
    const { container } = render(TagInput, {
      props: { tags: [], id: "test" },
    })
    const input = container.querySelector(
      "input[type='text']",
    ) as HTMLInputElement
    await fireEvent.input(input, { target: { value: "newtag" } })
    await fireEvent.keyDown(input, { key: "Enter" })

    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    expect(tagContainer.textContent).toContain("newtag")
    expect(input.value).toBe("")
  })

  it("adds a tag on comma", async () => {
    const { container } = render(TagInput, {
      props: { tags: [], id: "test" },
    })
    const input = container.querySelector(
      "input[type='text']",
    ) as HTMLInputElement
    await fireEvent.input(input, { target: { value: "commtag" } })
    await fireEvent.keyDown(input, { key: "," })

    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    expect(tagContainer.textContent).toContain("commtag")
  })

  it("does not add duplicate tags", async () => {
    const { container } = render(TagInput, {
      props: { tags: ["existing"], id: "test" },
    })
    const input = container.querySelector(
      "input[type='text']",
    ) as HTMLInputElement
    await fireEvent.input(input, { target: { value: "existing" } })
    await fireEvent.keyDown(input, { key: "Enter" })

    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    const badges = tagContainer.querySelectorAll(".badge")
    expect(badges).toHaveLength(1)
  })

  it("trims whitespace from tags", async () => {
    const { container } = render(TagInput, {
      props: { tags: [], id: "test" },
    })
    const input = container.querySelector(
      "input[type='text']",
    ) as HTMLInputElement
    await fireEvent.input(input, { target: { value: "  padded  " } })
    await fireEvent.keyDown(input, { key: "Enter" })

    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    expect(tagContainer.textContent).toContain("padded")
  })

  it("does not add empty tags", async () => {
    const { container } = render(TagInput, {
      props: { tags: [], id: "test" },
    })
    const input = container.querySelector(
      "input[type='text']",
    ) as HTMLInputElement
    await fireEvent.input(input, { target: { value: "   " } })
    await fireEvent.keyDown(input, { key: "Enter" })

    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    const badges = tagContainer.querySelectorAll(".badge")
    expect(badges).toHaveLength(0)
  })

  it("removes a tag when X button is clicked", async () => {
    const { container } = render(TagInput, {
      props: { tags: ["apple", "banana"], id: "test" },
    })
    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    const removeBtn = tagContainer.querySelector(
      'button[aria-label="Remove apple"]',
    ) as HTMLButtonElement
    await fireEvent.click(removeBtn)

    expect(tagContainer.textContent).not.toContain("apple")
    expect(tagContainer.textContent).toContain("banana")
  })

  it("removes the last tag on Backspace with empty input", async () => {
    const { container } = render(TagInput, {
      props: { tags: ["first", "second"], id: "test" },
    })
    const input = container.querySelector(
      "input[type='text']",
    ) as HTMLInputElement
    await fireEvent.keyDown(input, { key: "Backspace" })

    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    expect(tagContainer.textContent).toContain("first")
    expect(tagContainer.textContent).not.toContain("second")
  })

  it("splits comma-separated paste into multiple tags", async () => {
    const { container } = render(TagInput, {
      props: { tags: [], id: "test" },
    })
    const input = container.querySelector(
      "input[type='text']",
    ) as HTMLInputElement
    const clipboardData = {
      getData: (type: string) => (type === "text" ? "alpha, beta ,gamma" : ""),
    }
    await fireEvent.paste(input, { clipboardData })

    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    expect(tagContainer.textContent).toContain("alpha")
    expect(tagContainer.textContent).toContain("beta")
    expect(tagContainer.textContent).toContain("gamma")
    const badges = tagContainer.querySelectorAll(".badge")
    expect(badges).toHaveLength(3)
  })

  it("deduplicates tags on init", () => {
    const { container } = render(TagInput, {
      props: { tags: ["dup", "dup", "unique"], id: "test" },
    })
    const tagContainer = container.querySelector(
      '[data-testid="tag-input-test"]',
    )!
    const badges = tagContainer.querySelectorAll(".badge")
    expect(badges).toHaveLength(2)
  })

  it("renders the test id", () => {
    const { container } = render(TagInput, {
      props: { tags: [], id: "myfield" },
    })
    expect(
      container.querySelector('[data-testid="tag-input-myfield"]'),
    ).toBeTruthy()
  })
})
