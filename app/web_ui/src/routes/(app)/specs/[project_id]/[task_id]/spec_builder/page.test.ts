// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  render,
  fireEvent,
  cleanup,
  waitFor,
  screen,
} from "@testing-library/svelte"
import { tick } from "svelte"
import * as svelteMod from "svelte"

const {
  pageValue,
  mockPage,
  mockGet,
  mockCreateEvaluator,
  mockCreateEvalConfig,
} = vi.hoisted(() => {
  const pageValue = {
    params: { project_id: "proj1", task_id: "task1" },
    url: new URL("http://localhost/specs/proj1/task1/spec_builder"),
  }
  return {
    pageValue,
    mockPage: {
      subscribe(fn: (value: typeof pageValue) => void) {
        fn(pageValue)
        return () => {}
      },
    },
    mockGet: vi.fn(),
    mockCreateEvaluator: vi.fn(),
    mockCreateEvalConfig: vi.fn(),
  }
})

vi.mock("$app/stores", () => ({ page: mockPage }))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  beforeNavigate: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: { GET: mockGet, POST: vi.fn(), DELETE: vi.fn() },
}))

vi.mock("$lib/stores", () => ({
  load_task: vi.fn().mockResolvedValue({ id: "task1", name: "Task" }),
}))

vi.mock("$lib/stores/evals_store", () => ({
  set_current_eval_config: vi.fn().mockResolvedValue({}),
}))

vi.mock("$lib/agent", () => ({
  agentInfo: { set: vi.fn() },
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("$lib/api/v2_eval_api", () => ({
  createEvaluator: (...args: unknown[]) => mockCreateEvaluator(...args),
  createEvalConfig: (...args: unknown[]) => mockCreateEvalConfig(...args),
  checkAddCodeTrust: vi.fn().mockResolvedValue({ trusted: true }),
  addCodeTrust: vi.fn(),
}))

vi.mock("../../../../app_page.svelte", async () => {
  const Stub = await import("../__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

vi.mock("./create_spec_judge_form.svelte", async () => {
  const Stub = await import("./__tests__/create_spec_judge_form_stub.svelte")
  return { default: Stub.default }
})

vi.mock("./create_spec_form.svelte", async () => {
  const Stub = await import("./__tests__/create_spec_form_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/components/eval_types/trust_code_dialog.svelte", async () => {
  const Stub = await import("./__tests__/empty_stub.svelte")
  return { default: Stub.default }
})

const SpecBuilderPage = (await import("./+page.svelte")).default

beforeEach(() => {
  mockCreateEvaluator.mockResolvedValue({ id: "eval1" })
  mockCreateEvalConfig.mockResolvedValue({ id: "config1" })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

async function render_page(query: string) {
  pageValue.url = new URL(
    `http://localhost/specs/proj1/task1/spec_builder?${query}`,
  )
  const on_mount_callbacks: Array<() => unknown> = []
  const spy = vi
    .spyOn(svelteMod, "onMount")
    .mockImplementation((fn: () => unknown) => {
      on_mount_callbacks.push(fn)
    })
  const result = render(SpecBuilderPage)
  spy.mockRestore()
  for (const cb of on_mount_callbacks) {
    await cb()
  }
  await tick()
  return result
}

describe("spec builder judge-only save", () => {
  it("creates the judge eval config with human-origin provenance", async () => {
    const { findByTestId } = await render_page("judge=exact_match")

    await fireEvent.click(await findByTestId("judge-form-save"))

    await waitFor(() => expect(mockCreateEvalConfig).toHaveBeenCalledTimes(1))
    const [project_id, task_id, eval_id, request] =
      mockCreateEvalConfig.mock.calls[0]
    expect([project_id, task_id, eval_id]).toEqual(["proj1", "task1", "eval1"])
    expect(request.provenance).toEqual({ origin: "human" })
  })
})

describe("spec builder template name prefill", () => {
  async function spec_name() {
    return (await screen.findByTestId("spec-name")).getAttribute("data-name")
  }
  // One timer turn is enough: the check's response is applied in microtasks.
  const settle = () => new Promise((resolve) => setTimeout(resolve))

  it("replaces a taken template name with the free one", async () => {
    mockGet.mockResolvedValue({ data: { name: "Toxicity 2", was_taken: true } })
    await render_page("type=toxicity")

    await waitFor(async () => expect(await spec_name()).toBe("Toxicity 2"))
  })

  it("keeps a free template name and checks it for this task", async () => {
    mockGet.mockResolvedValue({ data: { name: "Toxicity", was_taken: false } })
    await render_page("type=toxicity")

    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        "/api/projects/{project_id}/tasks/{task_id}/available_spec_name",
        {
          params: {
            path: { project_id: "proj1", task_id: "task1" },
            query: { name: "Toxicity" },
          },
        },
      ),
    )
    await settle()
    expect(await spec_name()).toBe("Toxicity")
  })

  it.each([
    ["returns an error", () => mockGet.mockResolvedValue({ error: "boom" })],
    ["throws", () => mockGet.mockRejectedValue(new Error("offline"))],
  ])("keeps the template name when the check %s", async (_, fail) => {
    fail()
    await render_page("type=toxicity")

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))
    await settle()
    expect(await spec_name()).toBe("Toxicity")
  })

  it("keeps a name typed before the check returns", async () => {
    let resolve_check: (value: unknown) => void = () => {}
    mockGet.mockReturnValue(new Promise((resolve) => (resolve_check = resolve)))
    await render_page("type=toxicity")

    const field = await screen.findByTestId("spec-name")
    await fireEvent.input(field, { target: { value: "My Toxicity" } })
    expect(mockGet).toHaveBeenCalledTimes(1)
    resolve_check({ data: { name: "Toxicity 2", was_taken: true } })
    await settle()

    expect(await spec_name()).toBe("My Toxicity")
  })

  it.each(["desired_behaviour", "issue"])(
    "skips the check when the %s template starts unnamed",
    async (spec_type) => {
      await render_page(`type=${spec_type}`)

      expect(await spec_name()).toBe("")
      expect(mockGet).not.toHaveBeenCalled()
    },
  )
})
