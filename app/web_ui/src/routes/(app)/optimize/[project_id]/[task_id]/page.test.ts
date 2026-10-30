// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte"
import { tick } from "svelte"
import { get_task_composite_id } from "$lib/stores"
import { run_configs_by_task_composite_id } from "$lib/stores/run_configs_store"
import { make_agent_config } from "$lib/utils/lineage/__tests__/lineage_fixtures"

const { mockPage, mockGoto, mockLoadTask } = vi.hoisted(() => {
  type PageValue = { params: Record<string, string>; url: URL }
  const pageValue: PageValue = {
    params: { project_id: "proj1", task_id: "task1" },
    url: new URL("http://localhost/optimize/proj1/task1"),
  }
  return {
    mockPage: {
      subscribe(fn: (v: PageValue) => void) {
        fn(pageValue)
        return () => {}
      },
    },
    mockGoto: vi.fn(),
    mockLoadTask: vi.fn(),
  }
})

vi.mock("$app/stores", () => ({ page: mockPage }))
vi.mock("$app/navigation", () => ({ goto: mockGoto }))
vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))
vi.mock("$lib/stores", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores")>()),
  load_task: mockLoadTask,
  load_model_info: vi.fn().mockResolvedValue(undefined),
  load_available_tools: vi.fn(),
}))
vi.mock("$lib/stores/prompts_store", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores/prompts_store")>()),
  load_task_prompts: vi.fn().mockResolvedValue(undefined),
}))
vi.mock("$lib/stores/run_configs_store", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores/run_configs_store")>()),
  load_task_run_configs: vi.fn().mockResolvedValue(undefined),
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

const LINEAGE_PATH = "/optimize/proj1/task1/experiment_lineage"

async function render_page() {
  const result = render(Page)
  await tick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await tick()
  return result
}

function header_button_labels(): string[] {
  const row = screen.getByRole("button", {
    name: "Create Run Config",
  }).parentElement
  if (!row) {
    throw new Error("Run Configurations header buttons not found")
  }
  return [...row.querySelectorAll("button")].map(
    (button) => button.textContent?.trim() ?? "",
  )
}

async function open_row_menu(container: HTMLElement): Promise<string[]> {
  const trigger = container.querySelector('[aria-label="More options"]')
  if (!trigger) {
    throw new Error("row menu trigger not found")
  }
  await fireEvent.click(trigger)
  return [...document.querySelectorAll("ul.menu button")].map(
    (button) => button.textContent?.trim() ?? "",
  )
}

describe("Optimize +page.svelte entry points to Experiment Lineage", () => {
  beforeEach(() => {
    mockGoto.mockReset()
    mockLoadTask.mockReset()
    mockLoadTask.mockResolvedValue({ id: "task1", name: "Support Bot" })
    run_configs_by_task_composite_id.set({
      [get_task_composite_id("proj1", "task1")]: [
        make_agent_config({ id: "rc_1", name: "Gusty Forest" }),
      ],
    })
  })

  afterEach(() => {
    cleanup()
    run_configs_by_task_composite_id.set({})
  })

  it("shows Experiment Lineage first in the header and opens the page", async () => {
    await render_page()

    expect(header_button_labels()).toEqual([
      "Experiment Lineage",
      "Compare",
      "Create Run Config",
    ])
    await fireEvent.click(
      screen.getByRole("button", { name: "Experiment Lineage" }),
    )
    expect(mockGoto).toHaveBeenCalledWith(LINEAGE_PATH)
  })

  it("hides the header button in select mode and restores it on cancel", async () => {
    await render_page()

    await fireEvent.click(screen.getByRole("button", { name: "Compare" }))
    expect(
      screen.queryByRole("button", { name: "Experiment Lineage" }),
    ).toBeNull()

    await fireEvent.click(
      screen.getByRole("button", { name: "Cancel Selection" }),
    )
    expect(
      screen.getByRole("button", { name: "Experiment Lineage" }),
    ).toBeTruthy()
  })

  it("opens the page with the row's run config selected from its menu", async () => {
    const { container } = await render_page()

    const labels = await open_row_menu(container)
    expect(labels).toEqual([
      "Clone",
      "Set as Task Default",
      "Show in Experiment Lineage",
    ])
    await fireEvent.click(
      screen.getByRole("button", { name: "Show in Experiment Lineage" }),
    )
    expect(mockGoto).toHaveBeenCalledOnce()
    expect(mockGoto).toHaveBeenCalledWith(`${LINEAGE_PATH}?selected=rc_1`)
  })
})
