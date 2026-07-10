// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"

const mockPost = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

vi.mock("$lib/stores/prompts_store", () => ({
  load_task_prompts: vi.fn().mockResolvedValue(undefined),
}))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  beforeNavigate: vi.fn(),
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

import PromptForm from "./prompt_form.svelte"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

beforeEach(() => {
  mockPost.mockReset()
  mockPost.mockResolvedValue({ data: { id: "new-prompt-id" }, error: null })
})

async function set_input(container: HTMLElement, id: string, value: string) {
  const el = container.querySelector(`#${id}`) as
    | HTMLInputElement
    | HTMLTextAreaElement
  await fireEvent.input(el, { target: { value } })
  await tick()
}

describe("PromptForm provenance stamping", () => {
  it("fresh create sends human-origin provenance with no parent", async () => {
    const { container, getByText } = render(PromptForm, {
      props: { project_id: "proj1", task_id: "task1" },
    })
    await tick()

    await set_input(container, "prompt_name", "My Prompt")
    await set_input(container, "prompt", "You are a helpful assistant.")

    await fireEvent.click(getByText("Create Prompt"))
    await tick()

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const body = mockPost.mock.calls[0][1].body
    expect(body.provenance).toEqual({ origin: "human" })
  })

  it("clone create stamps derived_from_ids with the source prompt id", async () => {
    const { container, getByText } = render(PromptForm, {
      props: {
        project_id: "proj1",
        task_id: "task1",
        clone_mode: true,
        clone_source_prompt_id: "src-prompt-id",
      },
    })
    await tick()

    await set_input(container, "prompt_name", "Copy of My Prompt")
    await set_input(container, "prompt", "You are a helpful assistant.")

    await fireEvent.click(getByText("Clone Prompt"))
    await tick()

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const body = mockPost.mock.calls[0][1].body
    expect(body.provenance).toEqual({
      origin: "human",
      derived_from_ids: ["src-prompt-id"],
    })
  })
})
