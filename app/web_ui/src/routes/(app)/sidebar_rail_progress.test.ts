// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render } from "@testing-library/svelte"
import { progress_ui_state } from "$lib/stores/progress_ui_store"

// ProgressWidget subscribes to $app/stores "page" which is only available in
// a live SvelteKit request context. Stub it for this test so we can verify
// sidebar_rail_progress's own conditional rendering.
vi.mock("$lib/ui/progress_widget.svelte", async () => {
  const StubModule = await import(
    "./__tests__/sidebar_rail_progress_widget_stub.svelte"
  )
  return { default: StubModule.default }
})

// Import the component under test after the mock is registered.
const SidebarRailProgress = (await import("./sidebar_rail_progress.svelte"))
  .default

describe("SidebarRailProgress", () => {
  beforeEach(() => {
    progress_ui_state.set(null)
  })

  afterEach(() => {
    progress_ui_state.set(null)
  })

  it("renders nothing when progress_ui_state is null", () => {
    const { container } = render(SidebarRailProgress)
    expect(container.querySelector('[aria-label="In progress"]')).toBeNull()
    expect(container.querySelector('[aria-label="Progress"]')).toBeNull()
  })

  it("renders the pip and floating region when progress_ui_state is set", () => {
    progress_ui_state.set({
      title: "Running",
      body: "Step 1 of 3",
      cta: null,
      link: "/",
      progress: 0.33,
      step_count: 3,
      current_step: 1,
    })
    const { container } = render(SidebarRailProgress)
    expect(container.querySelector('[aria-label="In progress"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Progress"]')).not.toBeNull()
  })
})
