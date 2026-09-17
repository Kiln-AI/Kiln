// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const mockPost = vi.fn()
const mockGet = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

vi.mock("$lib/stores", () => ({
  load_current_task: vi.fn().mockResolvedValue(undefined),
  get_task_composite_id: (project_id: string, task_id: string) =>
    `${project_id}::${task_id}`,
}))

import { save_new_task_run_config } from "./run_configs_store"
import type { RunConfigProperties } from "$lib/types"

const run_config_properties: RunConfigProperties = {
  type: "kiln_agent",
  model_name: "gpt-4o",
  model_provider_name: "openai",
  prompt_id: "simple_prompt_builder",
  temperature: 1,
  top_p: 1,
  structured_output_mode: "default",
  thinking_level: null,
  input_transform: null,
  tools_config: { tools: [] },
}

beforeEach(() => {
  mockPost.mockReset()
  mockGet.mockReset()
  // Save reloads the run configs list after a successful POST.
  mockGet.mockResolvedValue({ data: [], error: null })
  mockPost.mockResolvedValue({ data: { id: "new-rc-id" }, error: null })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("save_new_task_run_config provenance wiring", () => {
  it("defaults to null provenance when the caller passes none", async () => {
    await save_new_task_run_config(
      "proj1",
      "task1",
      run_config_properties,
      "my-config",
    )

    const post_call = mockPost.mock.calls[0]
    expect(post_call[0]).toBe(
      "/api/projects/{project_id}/tasks/{task_id}/run_configs",
    )
    expect(post_call[1].body.provenance).toBeNull()
  })

  it("forwards a clone provenance (origin + derived_from_ids) into the POST body", async () => {
    await save_new_task_run_config(
      "proj1",
      "task1",
      run_config_properties,
      "clone-config",
      { origin: "human", derived_from_ids: ["source-rc-id"] },
    )

    const post_call = mockPost.mock.calls[0]
    expect(post_call[1].body.provenance).toEqual({
      origin: "human",
      derived_from_ids: ["source-rc-id"],
    })
  })

  it("forwards a fresh human-origin provenance with no parent", async () => {
    await save_new_task_run_config(
      "proj1",
      "task1",
      run_config_properties,
      "fresh-config",
      { origin: "human" },
    )

    const post_call = mockPost.mock.calls[0]
    expect(post_call[1].body.provenance).toEqual({ origin: "human" })
  })
})
