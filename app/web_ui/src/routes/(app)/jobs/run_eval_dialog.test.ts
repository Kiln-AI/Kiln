// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, waitFor, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import { client } from "$lib/api_client"
import { ui_state, default_ui_state } from "$lib/stores"
import { run_configs_by_task_composite_id } from "$lib/stores/run_configs_store"
import RunEvalDialog from "./run_eval_dialog.svelte"

vi.mock("$lib/api_client", () => ({
  client: { GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() },
  base_url: "http://localhost:8757",
}))

vi.mock("$lib/stores/job_creators", () => ({
  create_eval_job: vi.fn(),
}))

// FancySelect relies on @floating-ui/dom, which is unavailable in jsdom.
vi.mock("@floating-ui/dom", () => ({
  computePosition: vi.fn().mockResolvedValue({ x: 0, y: 0 }),
  autoUpdate: vi.fn(() => () => {}),
  offset: vi.fn(),
}))

// HTMLDialogElement methods are not implemented in jsdom.
beforeEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).showModal = vi.fn()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).close = vi.fn()
})

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>

function set_task() {
  ui_state.set({
    ...default_ui_state,
    current_project_id: "p_1",
    current_task_id: "t_1",
  })
}

function set_no_task() {
  ui_state.set({ ...default_ui_state })
}

// Routes each GET to the right fixture based on its URL template.
function stub_endpoints() {
  run_configs_by_task_composite_id.set({})
  mockGET.mockImplementation((url: string) => {
    if (url.endsWith("/evals")) {
      return Promise.resolve({
        data: [{ id: "e_1", name: "Quality Eval" }],
        error: undefined,
      })
    }
    if (url.endsWith("/eval_configs")) {
      return Promise.resolve({
        data: [{ id: "ec_1", name: "Judge One" }],
        error: undefined,
      })
    }
    if (url.endsWith("/evals/{eval_id}")) {
      return Promise.resolve({
        data: { id: "e_1", name: "Quality Eval", current_config_id: "ec_1" },
        error: undefined,
      })
    }
    if (url.endsWith("/run_configs")) {
      return Promise.resolve({
        data: [
          {
            id: "rc_1",
            name: "Default Run",
            run_config_properties: { type: "mcp" },
          },
        ],
        error: undefined,
      })
    }
    if (url.endsWith("/tasks/{task_id}")) {
      return Promise.resolve({
        data: { id: "t_1", default_run_config_id: "rc_1" },
        error: undefined,
      })
    }
    return Promise.resolve({ data: null, error: undefined })
  })
}

function submit_button(): HTMLButtonElement {
  const btn = Array.from(document.body.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("Run eval"),
  )
  if (!btn) throw new Error("Run eval button not rendered")
  return btn as HTMLButtonElement
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  set_no_task()
})

describe("RunEvalDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows a 'select a task first' message and no submit when no task is selected", async () => {
    set_no_task()
    const { component } = render(RunEvalDialog)
    component.show()
    await tick()
    expect(document.body.textContent).toContain("Select a task first")
    expect(
      Array.from(document.body.querySelectorAll("button")).some((b) =>
        b.textContent?.includes("Run eval"),
      ),
    ).toBe(false)
    // No data should be fetched when there is no task.
    expect(mockGET).not.toHaveBeenCalled()
  })

  it("keeps submit disabled until the eval is chosen (judge + run method default automatically)", async () => {
    set_task()
    stub_endpoints()
    const { component } = render(RunEvalDialog)
    component.show()
    // The default run method resolves automatically and renders its label.
    await waitFor(() =>
      expect(document.body.textContent).toContain("Default Run"),
    )
    // The eval picker is still empty, so the job cannot be started yet.
    expect(submit_button().disabled).toBe(true)
  })

  // A controllable promise so a test can resolve responses out of order.
  function deferred<T>() {
    let resolve!: (value: T) => void
    const promise = new Promise<T>((r) => {
      resolve = r
    })
    return { promise, resolve }
  }

  // The judge picker's closed trigger renders the selected config's name (via
  // formatEvalConfigName, which starts with the config name).
  function judge_response(eval_id: string | undefined) {
    return eval_id === "e_a"
      ? [{ id: "ec_a1", name: "Judge A1" }]
      : [{ id: "ec_b1", name: "Judge B1" }]
  }

  // FancySelect cannot be opened in jsdom, so we drive the eval-selection
  // reactive path via the bindable `selected_eval_id` prop instead.
  it("resets the judge selection to the new eval's configs when the eval changes", async () => {
    set_task()
    run_configs_by_task_composite_id.set({})
    mockGET.mockImplementation(
      (url: string, opts?: { params?: { path?: { eval_id?: string } } }) => {
        const eval_id = opts?.params?.path?.eval_id
        if (url.endsWith("/evals")) {
          return Promise.resolve({
            data: [
              { id: "e_a", name: "Eval A" },
              { id: "e_b", name: "Eval B" },
            ],
            error: undefined,
          })
        }
        if (url.endsWith("/evals/{eval_id}/eval_configs")) {
          return Promise.resolve({
            data: judge_response(eval_id),
            error: undefined,
          })
        }
        if (url.endsWith("/evals/{eval_id}")) {
          return Promise.resolve({
            data: {
              id: eval_id,
              current_config_id: eval_id === "e_a" ? "ec_a1" : "ec_b1",
            },
            error: undefined,
          })
        }
        if (url.endsWith("/run_configs")) {
          return Promise.resolve({ data: [], error: undefined })
        }
        if (url.endsWith("/tasks/{task_id}")) {
          return Promise.resolve({ data: { id: "t_1" }, error: undefined })
        }
        return Promise.resolve({ data: null, error: undefined })
      },
    )

    const { component } = render(RunEvalDialog)
    component.show()
    await tick()

    // Select eval A: judge A1 populates and is shown as selected.
    component.$set({ selected_eval_id: "e_a" })
    await waitFor(() => expect(document.body.textContent).toContain("Judge A1"))
    expect(document.body.textContent).not.toContain("Judge B1")

    // Switch to eval B: the judge list/selection resets to B's config.
    component.$set({ selected_eval_id: "e_b" })
    await waitFor(() => expect(document.body.textContent).toContain("Judge B1"))
    expect(document.body.textContent).not.toContain("Judge A1")
  })

  it("ignores a delayed eval-A response that resolves after switching to eval B (race guard)", async () => {
    set_task()
    run_configs_by_task_composite_id.set({})

    // Hold eval A's GETs open so they can resolve AFTER we switch to eval B.
    const a_eval = deferred<unknown>()
    const a_configs = deferred<unknown>()

    mockGET.mockImplementation(
      (url: string, opts?: { params?: { path?: { eval_id?: string } } }) => {
        const eval_id = opts?.params?.path?.eval_id
        if (url.endsWith("/evals")) {
          return Promise.resolve({
            data: [
              { id: "e_a", name: "Eval A" },
              { id: "e_b", name: "Eval B" },
            ],
            error: undefined,
          })
        }
        if (url.endsWith("/evals/{eval_id}/eval_configs")) {
          if (eval_id === "e_a") return a_configs.promise
          return Promise.resolve({
            data: judge_response(eval_id),
            error: undefined,
          })
        }
        if (url.endsWith("/evals/{eval_id}")) {
          if (eval_id === "e_a") return a_eval.promise
          return Promise.resolve({
            data: { id: eval_id, current_config_id: "ec_b1" },
            error: undefined,
          })
        }
        if (url.endsWith("/run_configs")) {
          return Promise.resolve({ data: [], error: undefined })
        }
        if (url.endsWith("/tasks/{task_id}")) {
          return Promise.resolve({ data: { id: "t_1" }, error: undefined })
        }
        return Promise.resolve({ data: null, error: undefined })
      },
    )

    const { component } = render(RunEvalDialog)
    component.show()
    await tick()

    // Pick eval A — its GETs are pending. Then quickly switch to eval B, whose
    // GETs resolve immediately and populate Judge B1.
    component.$set({ selected_eval_id: "e_a" })
    await tick()
    component.$set({ selected_eval_id: "e_b" })
    await waitFor(() => expect(document.body.textContent).toContain("Judge B1"))

    // Now let eval A's stale responses resolve. They must NOT clobber B's
    // state. Without the guard, A's late response would overwrite the judge
    // list back to "Judge A1".
    a_eval.resolve({
      data: { id: "e_a", current_config_id: "ec_a1" },
      error: undefined,
    })
    a_configs.resolve({ data: judge_response("e_a"), error: undefined })
    // Flush A's full promise chain (two awaits + the state assignment) and the
    // resulting reactive updates so a regression would actually surface.
    for (let i = 0; i < 5; i++) {
      await Promise.resolve()
      await tick()
    }

    expect(document.body.textContent).toContain("Judge B1")
    expect(document.body.textContent).not.toContain("Judge A1")
  })
})
