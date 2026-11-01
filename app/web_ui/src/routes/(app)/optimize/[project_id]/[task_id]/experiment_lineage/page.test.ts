// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render } from "@testing-library/svelte"
import { tick } from "svelte"

const { mockPage, set_task, run_config_loads } = vi.hoisted(() => {
  type PageValue = { params: Record<string, string>; url: URL }
  const page_for = (task_id: string): PageValue => ({
    params: { project_id: "proj1", task_id },
    url: new URL(
      `http://localhost/optimize/proj1/${task_id}/experiment_lineage`,
    ),
  })
  let value = page_for("task_a")
  const subscribers = new Set<(v: PageValue) => void>()
  const run_config_loads: {
    resolve: () => void
    reject: (e: Error) => void
  }[] = []
  return {
    mockPage: {
      subscribe(fn: (v: PageValue) => void) {
        subscribers.add(fn)
        fn(value)
        return () => subscribers.delete(fn)
      },
    },
    set_task(task_id: string) {
      value = page_for(task_id)
      subscribers.forEach((fn) => fn(value))
    },
    run_config_loads,
  }
})

vi.mock("$app/stores", () => ({ page: mockPage }))
vi.mock("$app/navigation", () => ({ goto: vi.fn() }))
vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))
vi.mock("$lib/stores", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores")>()),
  load_model_info: vi.fn(() => Promise.resolve()),
  load_available_tools: vi.fn(() => Promise.resolve()),
}))
vi.mock("$lib/stores/prompts_store", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores/prompts_store")>()),
  load_task_prompts: vi.fn(() => Promise.resolve()),
}))
vi.mock("$lib/stores/run_configs_store", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores/run_configs_store")>()),
  load_task_run_configs: vi.fn(
    () =>
      new Promise<void>((resolve, reject) => {
        run_config_loads.push({ resolve, reject })
      }),
  ),
}))

const Page = (await import("./+page.svelte")).default

async function settle() {
  await tick()
  await new Promise((r) => setTimeout(r, 0))
  await tick()
}

describe("Experiment Lineage +page.svelte", () => {
  afterEach(() => {
    cleanup()
    run_config_loads.length = 0
  })

  it("ignores an older load of the same task after navigating away and back", async () => {
    const { container } = render(Page)
    set_task("task_b")
    await tick()
    set_task("task_a")
    await tick()
    expect(run_config_loads).toHaveLength(3)
    const [older_a, , latest_a] = run_config_loads

    older_a.reject(new Error("stale failure"))
    await settle()
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
    expect(container.textContent).not.toContain("stale failure")

    latest_a.resolve()
    await settle()
    expect(container.querySelector(".loading-spinner")).toBeNull()
    expect(container.textContent).not.toContain("stale failure")
    expect(container.textContent).toContain("No Run Configurations Yet")
  })
})
