// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"

const { mockPage } = vi.hoisted(() => {
  const page_value = {
    params: { project_id: "proj1" },
    // The examples dialog only exists on the code step of the wizard
    state: { wizard_step: "code" },
    url: new URL("http://localhost/tools/proj1/add_tools/code_tool"),
  }
  return {
    mockPage: {
      subscribe(fn: (value: typeof page_value) => void) {
        fn(page_value)
        return () => {}
      },
    },
  }
})

vi.mock("$app/stores", () => ({ page: mockPage }))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  pushState: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: { GET: vi.fn(), POST: vi.fn() },
}))

vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }))

vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))

vi.mock("../../../../app_page.svelte", async () => {
  const Stub = await import("./__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const Stub = await import("./__tests__/dialog_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/components/code_editor.svelte", async () => {
  const Stub = await import("./__tests__/passthrough_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/components/code_tools/code_tool_test_panel.svelte", async () => {
  const Stub = await import("./__tests__/passthrough_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/run_config_component/tools_selector.svelte", async () => {
  const Stub = await import("./__tests__/passthrough_stub.svelte")
  return { default: Stub.default }
})

const Page = (await import("./+page.svelte")).default

afterEach(() => {
  cleanup()
})

function render_example_tabs() {
  const { container } = render(Page)
  const tabs = container.querySelectorAll<HTMLButtonElement>('[role="tab"]')
  return { container, tabs }
}

// The eval-type version of this picker lives in code_eval_form.svelte and is
// tested alongside it. Both are maintained in place, so both are pinned.
describe("Code Tool page — example picker", () => {
  it("renders the examples as a named, wrapping boxed tab group", () => {
    const { container, tabs } = render_example_tabs()
    const tablist = container.querySelector('[role="tablist"]')

    expect(tablist?.getAttribute("aria-label")).toBe("Examples")
    expect(tablist?.classList.contains("tabs-boxed")).toBe(true)
    expect(tablist?.classList.contains("flex-wrap")).toBe(true)
    expect(tabs.length).toBe(3)
    expect(tabs[0].textContent?.trim()).toBe("Parallel with Retries")
  })

  it("wraps each label so an over-long one ellipsizes", () => {
    const { tabs } = render_example_tabs()
    // text-overflow is inert on .tab itself (a flex container), so the label
    // must stay inside a block child for truncation to work at all
    expect(tabs[0].querySelector("span")?.classList.contains("truncate")).toBe(
      true,
    )
  })

  it("switches the active example tab on click", async () => {
    const { tabs } = render_example_tabs()

    expect(tabs[0].getAttribute("aria-selected")).toBe("true")
    expect(tabs[0].classList.contains("tab-active")).toBe(true)

    await fireEvent.click(tabs[2])

    expect(tabs[0].getAttribute("aria-selected")).toBe("false")
    expect(tabs[2].getAttribute("aria-selected")).toBe("true")
    expect(tabs[2].classList.contains("tab-active")).toBe(true)
  })

  it("moves the active example tab with the arrow, home and end keys", async () => {
    const { tabs } = render_example_tabs()

    await fireEvent.keyDown(tabs[0], { key: "ArrowRight" })
    expect(tabs[1].getAttribute("aria-selected")).toBe("true")
    expect(document.activeElement).toBe(tabs[1])

    // Wraps around both ends so the group is a single loop
    await fireEvent.keyDown(tabs[1], { key: "ArrowLeft" })
    await fireEvent.keyDown(tabs[0], { key: "ArrowLeft" })
    expect(tabs[2].getAttribute("aria-selected")).toBe("true")

    await fireEvent.keyDown(tabs[2], { key: "ArrowRight" })
    expect(tabs[0].getAttribute("aria-selected")).toBe("true")

    await fireEvent.keyDown(tabs[0], { key: "End" })
    expect(tabs[2].getAttribute("aria-selected")).toBe("true")

    await fireEvent.keyDown(tabs[2], { key: "Home" })
    expect(tabs[0].getAttribute("aria-selected")).toBe("true")
  })

  it("leaves keys it does not handle to the browser", async () => {
    const { tabs } = render_example_tabs()

    // fireEvent returns false when the default was prevented
    expect(await fireEvent.keyDown(tabs[0], { key: "ArrowDown" })).toBe(true)
    expect(tabs[0].getAttribute("aria-selected")).toBe("true")

    // Alt+Left is browser Back, so the tab group must not swallow it
    expect(
      await fireEvent.keyDown(tabs[0], { key: "ArrowLeft", altKey: true }),
    ).toBe(true)
    expect(tabs[0].getAttribute("aria-selected")).toBe("true")
  })

  it("keeps only the active tab in the tab sequence and the panel reachable", async () => {
    const { container, tabs } = render_example_tabs()
    const panel = container.querySelector('[role="tabpanel"]')

    expect(tabs[0].getAttribute("tabindex")).toBe("0")
    expect(tabs[1].getAttribute("tabindex")).toBe("-1")
    // The panel scrolls horizontally, so it needs to be keyboard reachable
    expect(panel?.getAttribute("tabindex")).toBe("0")
    expect(panel?.getAttribute("aria-labelledby")).toBe(tabs[0].id)
    expect(tabs[0].getAttribute("aria-controls")).toBe(panel?.id)

    await fireEvent.click(tabs[1])

    expect(tabs[0].getAttribute("tabindex")).toBe("-1")
    expect(tabs[1].getAttribute("tabindex")).toBe("0")
    expect(panel?.getAttribute("aria-labelledby")).toBe(tabs[1].id)
  })

  it("shows the selected example's code in the panel", async () => {
    const { container, tabs } = render_example_tabs()
    const panel = container.querySelector('[role="tabpanel"]')
    const first_example_code = panel?.textContent
    expect(first_example_code).toContain("def run(")

    await fireEvent.click(tabs[1])

    expect(panel?.textContent).toContain("def run(")
    expect(panel?.textContent).not.toBe(first_example_code)
  })
})
