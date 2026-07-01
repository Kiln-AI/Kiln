// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"

vi.mock("$lib/ui/dialog.svelte", async () => {
  const Stub = await import("../__tests__/dialog_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/utils/format_expanded_content", () => ({
  formatExpandedContent: (text: string) => ({ isJson: false, value: text }),
}))

const TestRunBrowseDialog = (await import("./test_run_browse_dialog.svelte"))
  .default

afterEach(() => cleanup())

const runs = [
  {
    input: "hello",
    output: { output: "world" },
    created_at: "2026-01-01T00:00:00Z",
  },
] as never[]

function manualLink(container: HTMLElement): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.trim().includes("Add Manual Example"),
  )
}

describe("TestRunBrowseDialog manual example gating", () => {
  it("shows the manual example link when supported", () => {
    const { container } = render(TestRunBrowseDialog, {
      props: { available_runs: runs, manual_example_supported: true },
    })
    expect(manualLink(container)).toBeDefined()
  })

  it("shows the manual example link by default", () => {
    const { container } = render(TestRunBrowseDialog, {
      props: { available_runs: runs },
    })
    expect(manualLink(container)).toBeDefined()
  })

  it("hides the manual example link when unsupported", () => {
    const { container } = render(TestRunBrowseDialog, {
      props: { available_runs: runs, manual_example_supported: false },
    })
    expect(manualLink(container)).toBeUndefined()
  })
})
