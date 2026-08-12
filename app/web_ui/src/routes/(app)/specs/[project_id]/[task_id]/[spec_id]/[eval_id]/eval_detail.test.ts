// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const {
  mockPage,
  mockGoto,
  mockClientGET,
  setEvalResponse,
  setProgressResponse,
} = vi.hoisted(() => {
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

  const default_eval = {
    id: "eval1",
    name: "Test Eval",
    eval_set_filter_id: "tag::test",
    eval_configs_filter_id: "tag::golden",
    eval_configs: [],
    output_scores: [{ name: "accuracy", type: "five_star" }],
  }
  const default_progress = {
    dataset_size: 30,
    golden_dataset_size: 30,
    golden_dataset_not_rated_count: 0,
    golden_dataset_partially_rated_count: 0,
    current_eval_method: null,
    train_dataset_size: 0,
    val_dataset_size: 0,
  }
  let eval_response: Record<string, unknown> = default_eval
  let progress_response: Record<string, unknown> = default_progress
  const setEvalResponse = (v: Record<string, unknown> | null) => {
    eval_response = v ?? default_eval
  }
  const setProgressResponse = (v: Record<string, unknown> | null) => {
    progress_response = v ?? default_progress
  }

  const mockClientGET = vi.fn().mockImplementation((path: string) => {
    if (path.includes("/evals/") && path.includes("/progress")) {
      return Promise.resolve({ data: progress_response, error: null })
    }
    if (path.includes("/evals/")) {
      return Promise.resolve({ data: eval_response, error: null })
    }
    if (path.includes("/specs/")) {
      return Promise.resolve({
        data: { id: "spec1", name: "Test Spec" },
        error: null,
      })
    }
    return Promise.resolve({ data: null, error: null })
  })

  return {
    mockPage,
    mockGoto,
    mockClientGET,
    setEvalResponse,
    setProgressResponse,
  }
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

const tagFromFilterId = (id: string) =>
  id.startsWith("tag::") ? id.replace("tag::", "") : undefined

vi.mock("../../spec_utils", () => ({
  tagFromFilterId,
  // The real helper links only for a tag filter id it was actually given, so the stub
  // does the same, through the same tag extraction: a stub that always returns undefined
  // cannot tell "we passed the TaskRun-only accessor and got nothing" from "we passed the
  // wrong accessor", and one that skipped tagFromFilterId would link a non-tag filter the
  // real helper refuses.
  linkFromFilterId: (
    project_id: string,
    task_id: string,
    filter_id: string | null | undefined,
  ) => {
    if (!filter_id) {
      return undefined
    }
    const tag = tagFromFilterId(filter_id)
    return tag ? `/dataset/${project_id}/${task_id}?tags=${tag}` : undefined
  },
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

describe("eval detail page — dataset rows", () => {
  afterEach(() => {
    cleanup()
    setEvalResponse(null)
    setProgressResponse(null)
  })

  async function rendered_properties(): Promise<
    Array<Record<string, string | undefined>>
  > {
    const { container } = render(EvalDetailPage)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    const lists = container.querySelectorAll(
      "[data-testid='property-list-stub']",
    )
    return Array.from(lists).flatMap((list) =>
      JSON.parse(list.getAttribute("data-properties") ?? "[]"),
    )
  }

  function row(
    properties: Array<Record<string, string | undefined>>,
    name: string,
  ) {
    return properties.find((property) => property.name === name)
  }

  it("renders a legacy eval's dataset rows from its flat fields", async () => {
    setEvalResponse({
      id: "eval1",
      name: "Test Eval",
      eval_set_filter_id: "tag::test",
      train_set_filter_id: "tag::train",
      eval_configs_filter_id: "tag::golden",
      splits: {},
      eval_configs: [],
      output_scores: [{ name: "accuracy", type: "five_star" }],
    })
    setProgressResponse({
      dataset_size: 30,
      golden_dataset_size: 30,
      golden_dataset_not_rated_count: 0,
      golden_dataset_partially_rated_count: 0,
      current_eval_method: null,
      train_dataset_size: 7,
      val_dataset_size: 0,
    })

    const properties = await rendered_properties()

    expect(row(properties, "Test Dataset")?.value).toBe("tag::test (30 items)")
    expect(row(properties, "Test Dataset")?.link).toContain("tags=test")
    expect(row(properties, "Training Dataset")?.value).toBe(
      "tag::train (7 items)",
    )
    // A legacy eval has no val split, and nothing mints one on load. The row still
    // renders so "no val set" is visible rather than absent, with no filter id, no
    // item count and no dataset link to point at.
    expect(row(properties, "Validation Dataset")?.value).toBe("Not configured")
    expect(row(properties, "Validation Dataset")?.link).toBeUndefined()
  })

  it("renders a splits-only eval's dataset rows, including val", async () => {
    // The server omits a split from `splits` only when it wrote it to a legacy field,
    // so a V2 eval arrives with null flat fields and everything in `splits`. Reading
    // only the flat fields rendered "null (30 items)" here.
    setEvalResponse({
      id: "eval1",
      name: "Test Eval",
      eval_set_filter_id: null,
      train_set_filter_id: null,
      splits: {
        test: { source: "eval_input", filter_id: "tag::inputs" },
        train: { source: "task_run", filter_id: "tag::train_x" },
        val: { source: "task_run", filter_id: "tag::val_x" },
      },
      eval_configs: [],
      output_scores: [{ name: "accuracy", type: "five_star" }],
    })
    setProgressResponse({
      dataset_size: 30,
      golden_dataset_size: 0,
      golden_dataset_not_rated_count: 0,
      golden_dataset_partially_rated_count: 0,
      current_eval_method: null,
      train_dataset_size: 7,
      val_dataset_size: 3,
    })

    const properties = await rendered_properties()

    expect(row(properties, "Test Dataset")?.value).toBe(
      "tag::inputs (30 items)",
    )
    // The filter id is worth showing; a /dataset link built from it is not, because the
    // items are EvalInputs and that page lists task runs. This is the whole reason
    // task_run_split_filter_id exists next to eval_split_filter_id — swapping the two
    // would leave every value assertion here passing.
    expect(row(properties, "Test Dataset")?.link).toBeUndefined()
    expect(row(properties, "Training Dataset")?.value).toBe(
      "tag::train_x (7 items)",
    )
    expect(row(properties, "Training Dataset")?.link).toContain("tags=train_x")
    expect(row(properties, "Validation Dataset")?.value).toBe(
      "tag::val_x (3 items)",
    )
    expect(row(properties, "Validation Dataset")?.link).toContain("tags=val_x")
  })
})
