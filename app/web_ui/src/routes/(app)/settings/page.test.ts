// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import Page from "./+page.svelte"
import { update_info, default_update_state } from "$lib/utils/update"
import {
  ui_state,
  default_ui_state,
  current_project,
  current_task,
  projects,
} from "$lib/stores"

afterEach(() => {
  cleanup()
  update_info.set(default_update_state)
  ui_state.set(default_ui_state)
  current_project.set(null)
  current_task.set(null)
  projects.set(null)
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

  it("keeps the 'Check for Update' item in the Application section regardless of update state", () => {
    update_info.set(default_update_state)
    const { container } = render(Page)
    const rowLabels = Array.from(
      container.querySelectorAll('[data-testid="settings-row"]'),
    ).map((b) => b.textContent?.trim())
    expect(rowLabels.some((t) => t?.includes("Check for Update"))).toBe(true)
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
    const rowLabels = Array.from(
      container.querySelectorAll('[data-testid="settings-row"]'),
    ).map((b) => b.textContent?.trim())
    expect(rowLabels.some((t) => t?.includes("Check for Update"))).toBe(true)
  })
})

describe("Settings +page.svelte — section structure", () => {
  it("renders the four sections in the expected order", () => {
    const { container } = render(Page)
    const headingTexts = Array.from(container.querySelectorAll("h2")).map((h) =>
      h.textContent?.trim(),
    )
    expect(headingTexts).toEqual([
      "Workspace",
      "Models & Providers",
      "Application",
      "About",
    ])
  })

  it("renders each row with its expected label and href/action target", () => {
    ui_state.set({
      current_project_id: "proj-1",
      current_task_id: "task-1",
      selected_model: null,
    })
    const { container } = render(Page)
    const rows = Array.from(
      container.querySelectorAll<HTMLElement>('[data-testid="settings-row"]'),
    )

    const expected: Array<{
      label: string
      href?: string
      tag: "A" | "BUTTON"
      external?: boolean
    }> = [
      {
        label: "Edit Current Task",
        href: "/settings/edit_task/proj-1/task-1",
        tag: "A",
      },
      {
        label: "Edit Current Project",
        href: "/settings/edit_project/proj-1",
        tag: "A",
      },
      { label: "Manage Projects", href: "/settings/manage_projects", tag: "A" },
      { label: "AI Providers", href: "/settings/providers", tag: "A" },
      {
        label: "Custom Models",
        href: "/settings/providers/add_models",
        tag: "A",
      },
      { label: "Application Logs", tag: "BUTTON" },
      {
        label: "Check for Update",
        href: "/settings/check_for_update",
        tag: "A",
      },
      {
        label: "Docs & Getting Started",
        href: "https://docs.kiln.tech",
        tag: "A",
        external: true,
      },
      {
        label: "License Agreement",
        href: "https://github.com/Kiln-AI/Kiln/blob/main/app/EULA.md",
        tag: "A",
        external: true,
      },
    ]

    expect(rows).toHaveLength(expected.length)
    rows.forEach((row, i) => {
      const exp = expected[i]
      expect(row.tagName).toBe(exp.tag)
      expect(row.textContent).toContain(exp.label)
      if (exp.href) {
        expect(row.getAttribute("href")).toBe(exp.href)
      }
      if (exp.external) {
        expect(row.getAttribute("target")).toBe("_blank")
        expect(row.getAttribute("rel")).toBe("noopener noreferrer")
      } else if (exp.tag === "A") {
        expect(row.getAttribute("target")).toBeNull()
      }
    })
  })
})
