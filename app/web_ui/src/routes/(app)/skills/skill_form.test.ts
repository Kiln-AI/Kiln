// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"

const mockPost = vi.fn()
const mockGet = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

vi.mock("$lib/stores", () => ({
  uncache_available_tools: vi.fn(),
}))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  beforeNavigate: vi.fn(),
}))

import SkillForm from "./skill_form.svelte"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

beforeEach(() => {
  mockPost.mockReset()
  mockGet.mockReset()
  mockPost.mockResolvedValue({ data: { id: "new-skill-id" }, error: null })
})

async function set_input(container: HTMLElement, id: string, value: string) {
  const el = container.querySelector(`#${id}`) as
    | HTMLInputElement
    | HTMLTextAreaElement
  await fireEvent.input(el, { target: { value } })
  await tick()
}

async function submit(getByText: (t: string) => HTMLElement, label: string) {
  await fireEvent.click(getByText(label))
  await tick()
}

describe("SkillForm provenance stamping", () => {
  it("fresh create sends human-origin provenance with no parent", async () => {
    const { container, getByText } = render(SkillForm, {
      props: { project_id: "proj1" },
    })
    await tick()

    await set_input(container, "skill_name", "test-skill")
    await set_input(container, "skill_description", "A test skill")
    await set_input(container, "skill_body", "Do the thing.")

    await submit(getByText, "Add")

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const body = mockPost.mock.calls[0][1].body
    expect(body.provenance).toEqual({ origin: "human" })
  })

  it("clone create stamps derived_from_ids with the source skill id", async () => {
    // clone_mode + skill_id is what drives lineage; the derived_from_ids value
    // is the source id prop, independent of the (separately-tested) source prefill.
    const { container, getByText } = render(SkillForm, {
      props: {
        project_id: "proj1",
        skill_id: "src-skill-id",
        clone_mode: true,
      },
    })
    await tick()

    await set_input(container, "skill_name", "copy-of-source-skill")
    await set_input(container, "skill_description", "Cloned desc")
    await set_input(container, "skill_body", "Cloned body")

    await submit(getByText, "Clone")

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const body = mockPost.mock.calls[0][1].body
    expect(body.provenance).toEqual({
      origin: "human",
      derived_from_ids: ["src-skill-id"],
    })
  })
})
