// @vitest-environment jsdom
import {
  describe,
  it,
  expect,
  afterEach,
  beforeAll,
  beforeEach,
  vi,
} from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import type { ComponentProps } from "svelte"

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

// These URL tests are about the run-comparison-jobs URL shape; mock the
// project-scoped jobs store so the store-derived "is running" overlay sees
// an empty job list and the component renders the idle "Run Eval" button.
vi.mock("$lib/stores/jobs_store", () => ({
  jobs: {
    subscribe: (run: (value: unknown[]) => void) => {
      run([])
      return () => {}
    },
  },
}))

const event_source_urls: string[] = []

class FakeEventSource {
  url: string
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  constructor(url: string) {
    this.url = url
    event_source_urls.push(url)
  }
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource)

// jsdom doesn't implement <dialog>.showModal/close; the Run Eval flow opens a
// dialog before building the EventSource URL, so polyfill them as no-ops.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true
  }
  HTMLDialogElement.prototype.close = function () {
    this.open = false
  }
})

const RunEval = (await import("./run_eval.svelte")).default

async function open_and_run(
  props: ComponentProps<InstanceType<typeof RunEval>>,
) {
  const { getAllByText } = render(RunEval, { props })
  // Open the run dialog, then confirm to build the EventSource URL.
  await fireEvent.click(getAllByText(/^Run Eval$/)[0])
  const confirm = getAllByText(/^Run Eval$/).at(-1)
  await fireEvent.click(confirm as HTMLElement)
}

describe("run_eval.svelte run_config URL", () => {
  beforeEach(() => {
    event_source_urls.length = 0
  })
  afterEach(() => {
    cleanup()
  })

  it("hits run_comparison_jobs with explicit run_config_ids", async () => {
    await open_and_run({
      eval_type: "run_config",
      project_id: "p1",
      task_id: "t1",
      eval_id: "e1",
      current_eval_config_id: "ec1",
      run_all: false,
      run_config_ids: ["rc1", "rc2"],
    })

    expect(event_source_urls).toHaveLength(1)
    const url = new URL(event_source_urls[0])
    expect(url.pathname).toBe(
      "/api/projects/p1/tasks/t1/evals/e1/eval_config/ec1/run_comparison_jobs",
    )
    expect(url.searchParams.get("all_run_configs")).toBe("false")
    expect(url.searchParams.getAll("run_config_ids")).toEqual(["rc1", "rc2"])
  })

  it("hits run_comparison_jobs with all_run_configs when run_all", async () => {
    await open_and_run({
      eval_type: "run_config",
      project_id: "p1",
      task_id: "t1",
      eval_id: "e1",
      current_eval_config_id: "ec1",
      run_all: true,
      run_config_ids: [],
    })

    expect(event_source_urls).toHaveLength(1)
    const url = new URL(event_source_urls[0])
    expect(url.pathname).toBe(
      "/api/projects/p1/tasks/t1/evals/e1/eval_config/ec1/run_comparison_jobs",
    )
    expect(url.searchParams.get("all_run_configs")).toBe("true")
    expect(url.searchParams.getAll("run_config_ids")).toEqual([])
  })
})
