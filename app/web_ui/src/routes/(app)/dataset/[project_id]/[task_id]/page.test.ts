// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import * as svelte from "svelte"
import { get, writable } from "svelte/store"
import type { RunSummary } from "$lib/types"
import { tag_store_by_task_id } from "$lib/stores/tag_store"

const { mockPage, mockClientGET } = vi.hoisted(() => {
  type PageValue = { params: Record<string, string>; url: URL }
  const pageValue: PageValue = {
    params: { project_id: "proj1", task_id: "task1" },
    url: new URL("http://localhost/dataset/proj1/task1"),
  }
  const mockPage = {
    subscribe(fn: (v: PageValue) => void) {
      fn(pageValue)
      return () => {}
    },
  }
  return { mockPage, mockClientGET: vi.fn() }
})

vi.mock("$app/stores", () => ({ page: mockPage }))
vi.mock("$app/navigation", () => ({ goto: vi.fn(), replaceState: vi.fn() }))
vi.mock("$lib/api_client", () => ({ client: { GET: mockClientGET } }))
vi.mock("$lib/stores", () => ({
  model_info: writable(null),
  load_model_info: vi.fn(),
  model_name: (id: string) => id,
}))
vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))

const Page = (await import("./+page.svelte")).default

const SUMMARIES_PATH =
  "/api/projects/{project_id}/tasks/{task_id}/runs_summaries"
const TAGS_PATH = "/api/projects/{project_id}/tasks/{task_id}/tags"

type SummariesResponse = { data: RunSummary[]; error: null }

const run_summary: RunSummary = {
  id: "run1",
  created_at: "2024-01-01T00:00:00Z",
  input_preview: "input",
  output_preview: "output",
  tags: ["golden"],
}

async function settle() {
  await svelte.tick()
  await new Promise((r) => setTimeout(r, 0))
  await svelte.tick()
}

function requested_paths(): string[] {
  return mockClientGET.mock.calls.map(([path]) => path as string)
}

describe("dataset +page.svelte", () => {
  let resolve_summaries: (response: SummariesResponse) => void = () => {}

  beforeEach(() => {
    // Under vitest, "svelte" resolves to its SSR build, where onMount never runs.
    // The tag picker loads the tag counts from onMount, so run each callback just
    // after its component is created.
    vi.spyOn(svelte, "onMount").mockImplementation((fn) => {
      queueMicrotask(() => void fn())
    })
    mockClientGET.mockReset()
    mockClientGET.mockImplementation((path: string) => {
      if (path === SUMMARIES_PATH) {
        return new Promise<SummariesResponse>((resolve) => {
          resolve_summaries = resolve
        })
      }
      if (path === TAGS_PATH) {
        return Promise.resolve({ data: { golden: 1 }, error: null })
      }
      return Promise.resolve({ data: null, error: null })
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    tag_store_by_task_id.set({})
  })

  it("requests the tag counts only after the run summaries arrive", async () => {
    render(Page)
    await settle()

    expect(requested_paths()).toEqual([SUMMARIES_PATH])

    resolve_summaries({ data: [run_summary], error: null })
    await settle()

    expect(requested_paths()).toEqual([SUMMARIES_PATH, TAGS_PATH])
    expect(mockClientGET.mock.calls[1][1]).toEqual({
      params: { path: { project_id: "proj1", task_id: "task1" } },
    })
    expect(get(tag_store_by_task_id)["task1"]).toEqual({ golden: 1 })
  })
})
