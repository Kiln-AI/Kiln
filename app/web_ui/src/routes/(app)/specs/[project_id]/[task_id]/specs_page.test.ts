// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const { mockPage, mockClientGET, setEvalsResponse } = vi.hoisted(() => {
  type PageValue = {
    params: Record<string, string>
    url: URL
  }
  const pageValue: PageValue = {
    params: { project_id: "proj1", task_id: "task1" },
    url: new URL("http://localhost/specs/proj1/task1"),
  }
  const mockPage = {
    subscribe(fn: (value: PageValue) => void) {
      fn(pageValue)
      return () => {}
    },
  }

  const default_evals_response = {
    evals: [
      {
        id: "eval1",
        name: "Test Eval",
        created_at: "2024-01-01T00:00:00Z",
        output_scores: [],
      },
    ],
    load_error_count: 0,
  }
  let evals_response: Record<string, unknown> = default_evals_response
  const setEvalsResponse = (v: Record<string, unknown> | null) => {
    evals_response = v ?? default_evals_response
  }

  const mockClientGET = vi.fn().mockImplementation((path: string) => {
    if (path.endsWith("/evals")) {
      return Promise.resolve({ data: evals_response, error: null })
    }
    if (path.endsWith("/specs")) {
      return Promise.resolve({ data: [], error: null })
    }
    if (path.includes("verify_kiln_copilot_api_key")) {
      return Promise.resolve({ data: { is_valid: false }, error: null })
    }
    return Promise.resolve({ data: null, error: null })
  })

  return { mockPage, mockClientGET, setEvalsResponse }
})

// Svelte 4 async onMount callbacks do not execute in jsdom/vitest, and the page keeps
// its loading state until the onMount copilot check settles. Run the callback inline.
vi.mock("svelte", async (importOriginal) => {
  const actual = await importOriginal<typeof import("svelte")>()
  return {
    ...actual,
    // @testing-library/svelte probes this Svelte 5 only export to pick a mount strategy.
    mount: undefined,
    onMount: (fn: () => unknown) => void fn(),
  }
})

vi.mock("$app/stores", () => ({
  page: mockPage,
}))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  replaceState: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: {
    GET: mockClientGET,
  },
}))

vi.mock("$lib/agent", () => ({
  agentInfo: { set: vi.fn() },
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("../../../app_page.svelte", async () => {
  const Stub = await import("./__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

// Dynamic import after all mocks
const SpecsPage = (await import("./+page.svelte")).default

const EXPECTED_TOOLTIP =
  "You may need to update Kiln. Some evals could not be opened by this version of Kiln."

async function render_page() {
  const result = render(SpecsPage)
  // The page has three independent loaders (specs, evals, copilot settings) and only
  // renders its body once all three settle, so flush a few macrotask turns.
  for (let i = 0; i < 5; i++) {
    await new Promise((r) => setTimeout(r, 0))
    await tick()
  }
  return result
}

describe("specs page — eval load error line", () => {
  afterEach(() => {
    cleanup()
    setEvalsResponse(null)
  })

  it("renders the plural error line and tooltip when several evals fail to load", async () => {
    setEvalsResponse({
      evals: [{ id: "eval1", name: "Test Eval", output_scores: [] }],
      load_error_count: 2,
    })

    const { container } = await render_page()

    const error_line = container.querySelector(".text-error")
    expect(error_line).not.toBeNull()
    expect(error_line?.textContent).toContain("2 evals failed to load")
    expect(error_line?.textContent).toContain(EXPECTED_TOOLTIP)
    expect(container.querySelector("[role='tooltip']")?.textContent).toContain(
      EXPECTED_TOOLTIP,
    )
  })

  it("renders the singular error line when exactly one eval fails to load", async () => {
    setEvalsResponse({
      evals: [{ id: "eval1", name: "Test Eval", output_scores: [] }],
      load_error_count: 1,
    })

    const { container } = await render_page()

    expect(container.textContent).toContain("1 eval failed to load")
    expect(container.textContent).not.toContain("1 evals failed to load")
    expect(container.textContent).toContain(EXPECTED_TOOLTIP)
  })

  it("renders nothing when no evals fail to load", async () => {
    setEvalsResponse({
      evals: [{ id: "eval1", name: "Test Eval", output_scores: [] }],
      load_error_count: 0,
    })

    const { container } = await render_page()

    expect(container.textContent).not.toContain("failed to load")
    expect(container.textContent).not.toContain(EXPECTED_TOOLTIP)
    expect(container.querySelector(".text-error")).toBeNull()
  })
})
