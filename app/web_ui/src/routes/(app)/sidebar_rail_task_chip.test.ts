// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import { current_task, current_project } from "$lib/stores"
import SidebarRailTaskChip from "./sidebar_rail_task_chip.svelte"
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
    const { container, component } = render(SidebarRailTaskChip)
    component.$on("open", handler)
    const button = container.querySelector("button") as HTMLElement
    await fireEvent.click(button)
    expect(handler).toHaveBeenCalledOnce()
  })

  it("renders a tooltip containing both task name and project name on hover", async () => {
    current_task.set({ name: "Apollo" } as AnyTask)
    current_project.set({ name: "Moon Shot" } as AnyProject)
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button") as HTMLElement
    await fireEvent.mouseEnter(button)
    const tooltip = container.querySelector('[role="tooltip"]')
    expect(tooltip).not.toBeNull()
    expect(tooltip?.textContent).toContain("Apollo")
    expect(tooltip?.textContent).toContain("Moon Shot")
  })

  it("omits the tooltip when neither task nor project name is set", async () => {
    const { container } = render(SidebarRailTaskChip)
    const button = container.querySelector("button") as HTMLElement
    await fireEvent.mouseEnter(button)
    expect(container.querySelector('[role="tooltip"]')).toBeNull()
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
