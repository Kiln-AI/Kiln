// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, fireEvent, waitFor, cleanup } from "@testing-library/svelte"
import { current_task, current_project } from "$lib/stores"
import SidebarRailTaskChip from "./sidebar_rail_task_chip.svelte"

// Tooltip is portaled to document.body via <Float portal>, not inside the
// render container. Clean up portaled nodes between tests to avoid leaks.
afterEach(() => {
  cleanup()
  document.body
    .querySelectorAll('[role="tooltip"]')
    .forEach((el) => el.remove())
})

function findTooltip(): HTMLElement | null {
  return document.body.querySelector('[role="tooltip"]')
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyTask = any
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyProject = any

describe("SidebarRailTaskChip", () => {
  beforeEach(() => {
    current_task.set(null)
    current_project.set(null)
  })

  afterEach(() => {
    current_task.set(null)
    current_project.set(null)
  })

  it("renders the uppercase first letter of the task name", () => {
    current_task.set({ name: "apollo" } as AnyTask)
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button")
    expect(button?.textContent?.trim()).toBe("A")
  })

  it("renders an empty chip when no task is selected", () => {
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button")
    expect(button?.textContent?.trim()).toBe("")
  })

  it("dispatches an open event when clicked", async () => {
    const handler = vi.fn()
    const { component, getByRole } = render(SidebarRailTaskChip)
    component.$on("open", handler)
    await fireEvent.click(getByRole("button"))
    expect(handler).toHaveBeenCalledOnce()
  })

  it("renders a tooltip containing both task name and project name on hover", async () => {
    current_task.set({ name: "Apollo" } as AnyTask)
    current_project.set({ name: "Moon Shot" } as AnyProject)
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button") as HTMLElement
    await fireEvent.mouseEnter(button)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    const tooltip = findTooltip()
    expect(tooltip?.textContent).toContain("Apollo")
    expect(tooltip?.textContent).toContain("Moon Shot")
  })

  it("wires aria-describedby from the button to the visible tooltip", async () => {
    current_task.set({ name: "Apollo" } as AnyTask)
    current_project.set({ name: "Moon Shot" } as AnyProject)
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button") as HTMLElement
    expect(button.getAttribute("aria-describedby")).toBeNull()
    await fireEvent.mouseEnter(button)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    const describedBy = button.getAttribute("aria-describedby")
    expect(describedBy).not.toBeNull()
    const described = document.getElementById(describedBy!)
    expect(described).not.toBeNull()
    expect(described?.textContent).toContain("Apollo")
    expect(described?.textContent).toContain("Moon Shot")
  })

  it("omits the tooltip when neither task nor project name is set", async () => {
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button") as HTMLElement
    await fireEvent.mouseEnter(button)
    expect(findTooltip()).toBeNull()
  })

  it("does not render a 'CURRENT TASK' header in the tooltip", async () => {
    current_task.set({ name: "Apollo" } as AnyTask)
    current_project.set({ name: "Moon Shot" } as AnyProject)
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button") as HTMLElement
    await fireEvent.mouseEnter(button)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    expect(findTooltip()?.textContent).not.toContain("CURRENT TASK")
  })

  it("uses the task name as the aria-label when a task is selected", () => {
    current_task.set({ name: "Apollo" } as AnyTask)
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button")
    expect(button?.getAttribute("aria-label")).toBe("Apollo")
  })

  it("falls back to 'Select task' aria-label when no task is set", () => {
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button")
    expect(button?.getAttribute("aria-label")).toBe("Select task")
  })
})
