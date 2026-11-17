// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte"

const { mockPage, mockGoto, pending } = vi.hoisted(() => {
  type PageValue = { params: Record<string, string>; url: URL }
  const pageValue: PageValue = {
    params: { project_id: "proj1", task_id: "task1" },
    url: new URL(
      "http://localhost/specs/proj1/task1/compare?from=optimize&columns=2&models=rc_1,",
    ),
  }
  return {
    mockPage: {
      subscribe(fn: (v: PageValue) => void) {
        fn(pageValue)
        return () => {}
      },
    },
    mockGoto: vi.fn(),
    // The header is the only thing under test, so the page's loads never finish.
    pending: () => new Promise<never>(() => {}),
  }
})

vi.mock("$app/stores", () => ({ page: mockPage }))
vi.mock("$app/navigation", () => ({ goto: mockGoto }))
vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))
vi.mock("$lib/stores", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores")>()),
  load_task: vi.fn(pending),
  load_model_info: vi.fn(pending),
  load_available_models: vi.fn(pending),
}))
vi.mock("$lib/stores/prompts_store", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores/prompts_store")>()),
  load_task_prompts: vi.fn(pending),
}))
vi.mock(
  "$lib/ui/run_config_component/create_new_run_config_dialog.svelte",
  async () => ({
    default: (
      await import(
        "$lib/ui/run_config_component/__tests__/create_new_run_config_dialog_stub.svelte"
      )
    ).default,
  }),
)

const Page = (await import("./+page.svelte")).default

describe("Compare +page.svelte", () => {
  afterEach(() => {
    cleanup()
    mockGoto.mockReset()
  })

  it("opens Experiment Lineage from the header, with nothing selected", async () => {
    render(Page)

    await fireEvent.click(
      screen.getByRole("button", { name: "Experiment Lineage" }),
    )
    expect(mockGoto).toHaveBeenCalledWith(
      "/optimize/proj1/task1/experiment_lineage",
    )
  })
})
