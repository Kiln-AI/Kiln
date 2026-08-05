// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const { mockPage, mockGoto, mockClientGET } = vi.hoisted(() => {
  type PageValue = {
    params: Record<string, string>
    url: URL
  }
  let pageValue: PageValue = {
    params: {
      project_id: "proj1",
      task_id: "task1",
      spec_id: "spec1",
      eval_id: "eval1",
    },
    url: new URL("http://localhost/specs/proj1/task1/spec1/eval1"),
  }
  type Subscriber = (value: PageValue) => void
  const subscribers = new Set<Subscriber>()
  const mockPage = {
    subscribe(fn: Subscriber) {
      subscribers.add(fn)
      fn(pageValue)
      return () => subscribers.delete(fn)
    },
    set(v: PageValue) {
      pageValue = v
      subscribers.forEach((fn) => fn(v))
    },
  }

  const mockGoto = vi.fn()

  const mockClientGET = vi.fn().mockImplementation((path: string) => {
    if (path.includes("/evals/") && path.includes("/progress")) {
      return Promise.resolve({
        data: {
          dataset_size: 30,
          golden_dataset_size: 30,
          golden_dataset_not_rated_count: 0,
          golden_dataset_partially_rated_count: 0,
          current_eval_method: null,
          train_dataset_size: 0,
        },
        error: null,
      })
    }
    if (path.includes("/evals/")) {
      return Promise.resolve({
        data: {
          id: "eval1",
          name: "Test Eval",
          eval_set_filter_id: "tag::test",
          eval_configs_filter_id: "tag::golden",
          eval_configs: [],
          output_scores: [{ name: "accuracy", type: "five_star" }],
        },
        error: null,
      })
    }
    if (path.includes("/specs/")) {
      return Promise.resolve({
        data: { id: "spec1", name: "Test Spec" },
        error: null,
      })
    }
    return Promise.resolve({ data: null, error: null })
  })

  return { mockPage, mockGoto, mockClientGET }
})

vi.mock("$app/stores", () => ({
  page: mockPage,
}))

vi.mock("$app/navigation", () => ({
  goto: mockGoto,
  beforeNavigate: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: {
    GET: mockClientGET,
  },
}))

vi.mock("$lib/stores", () => ({
  model_info: {
    subscribe: (fn: (v: null) => void) => {
      fn(null)
      return () => {}
    },
  },
  load_model_info: vi.fn(),
  model_name: () => "",
  load_available_models: vi.fn(),
}))

vi.mock("$lib/stores/progress_ui_store", () => ({
  progress_ui_state: {
    set: vi.fn(),
    subscribe: (fn: (v: null) => void) => {
      fn(null)
      return () => {}
    },
  },
}))

vi.mock("$lib/agent", () => ({
  agentInfo: { set: vi.fn() },
}))

// Stub heavy UI components with real .svelte stubs
vi.mock("../../../../../app_page.svelte", async () => {
  const Stub = await import("./__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/info_tooltip.svelte", async () => {
  const Stub = await import("./__tests__/info_tooltip_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/property_list.svelte", async () => {
  const Stub = await import("./__tests__/property_list_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/edit_dialog.svelte", async () => {
  const Stub = await import("./__tests__/edit_dialog_stub.svelte")
  return { default: Stub.default }
})

vi.mock("../../spec_utils", () => ({
  tagFromFilterId: (id: string) =>
    id.startsWith("tag::") ? id.replace("tag::", "") : undefined,
  linkFromFilterId: () => undefined,
}))

// Dynamic import after all mocks
const EvalDetailPage = (await import("./+page.svelte")).default

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("eval detail page — docs link removal (Phase 9)", () => {
  afterEach(() => {
    cleanup()
  })

  it("does not render 'Read the Docs' text anywhere on the page", async () => {
    const { container } = render(EvalDetailPage)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    expect(container.textContent).not.toContain("Read the Docs")
    expect(container.textContent).not.toContain("Read the docs")
  })

  it("does not pass sub_subtitle to AppPage", async () => {
    const { container } = render(EvalDetailPage)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    const appPage = container.querySelector("[data-testid='app-page-stub']")
    expect(appPage).not.toBeNull()
    expect(appPage?.getAttribute("data-sub-subtitle")).toBeNull()
  })

  it("does not pass sub_subtitle_link to AppPage", async () => {
    const { container } = render(EvalDetailPage)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    const appPage = container.querySelector("[data-testid='app-page-stub']")
    expect(appPage).not.toBeNull()
    expect(appPage?.getAttribute("data-sub-subtitle-link")).toBeNull()
  })

  it("does not contain any docs.kiln.tech URLs", async () => {
    const { container } = render(EvalDetailPage)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    expect(container.innerHTML).not.toContain("docs.kiln.tech")
  })
})
