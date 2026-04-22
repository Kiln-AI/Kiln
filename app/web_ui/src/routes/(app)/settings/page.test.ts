// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import Page from "./+page.svelte"
import { update_info, default_update_state } from "$lib/utils/update"

afterEach(() => {
  cleanup()
  update_info.set(default_update_state)
})

describe("Settings +page.svelte — Update Available callout", () => {
  it("does not render the Update Available callout when no update is available", () => {
    const { queryByTestId } = render(Page)
    expect(queryByTestId("update-available-callout")).toBeNull()
  })

  it("does not render the Update Available callout when update_result is null", () => {
    update_info.set({
      update_result: null,
      update_loading: false,
      update_error: null,
    })
    const { queryByTestId } = render(Page)
    expect(queryByTestId("update-available-callout")).toBeNull()
  })

  it("renders the Update Available callout with title, description, and link when has_update is true", () => {
    update_info.set({
      update_result: {
        has_update: true,
        latest_version: "1.0.0",
        link: "https://example.com",
      },
      update_loading: false,
      update_error: null,
    })
    const { getByTestId } = render(Page)
    const callout = getByTestId("update-available-callout")
    expect(callout).toBeDefined()
    expect(callout.textContent).toContain("Update Available")
    expect(callout.textContent).toContain(
      "A new version of Kiln is ready to install.",
    )
    const link = callout.querySelector("a")
    expect(link).not.toBeNull()
    expect(link?.getAttribute("href")).toBe("/settings/check_for_update")
    expect(link?.textContent?.trim()).toBe("View Update")
  })

  it("renders the Update Available callout before the first section heading when has_update is true", () => {
    update_info.set({
      update_result: {
        has_update: true,
        latest_version: "1.0.0",
        link: "https://example.com",
      },
      update_loading: false,
      update_error: null,
    })
    const { getByTestId, container } = render(Page)
    const callout = getByTestId("update-available-callout")
    const firstH2 = container.querySelector("h2")
    expect(firstH2).not.toBeNull()
    // DOCUMENT_POSITION_FOLLOWING (0x04) means firstH2 follows callout
    const position = callout.compareDocumentPosition(firstH2 as Node)
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("keeps the 'Check for Update' item in Help & Resources regardless of update state", () => {
    update_info.set(default_update_state)
    const { container } = render(Page)
    const headings = Array.from(container.querySelectorAll("h3")).map((h) =>
      h.textContent?.trim(),
    )
    expect(headings).toContain("Check for Update")
  })

  it("keeps the 'Check for Update' item when has_update is true", () => {
    update_info.set({
      update_result: {
        has_update: true,
        latest_version: "1.0.0",
        link: "https://example.com",
      },
      update_loading: false,
      update_error: null,
    })
    const { container } = render(Page)
    const itemNames = Array.from(container.querySelectorAll("h3")).map((h) =>
      h.textContent?.trim(),
    )
    expect(itemNames).toContain("Check for Update")
  })
})
