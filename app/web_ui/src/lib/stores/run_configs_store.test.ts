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

import {
  run_config_clone_parent_id,
  save_new_task_run_config,
} from "./run_configs_store"
import type { RunConfigProperties, TaskRunConfig } from "$lib/types"

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

describe("run_config_clone_parent_id", () => {
  const run_config = (id: string | null) =>
    ({ id, name: "rc", run_config_properties }) as TaskRunConfig

  it("returns the id of a saved run config", () => {
    expect(run_config_clone_parent_id(run_config("123456"))).toBe("123456")
  })

  it.each([
    ["a fine-tuned model's run config", "finetune_run_config::p1::t1::ft1"],
    ["a run config with no id", null],
  ])("returns null for %s", (_label, id) => {
    expect(run_config_clone_parent_id(run_config(id))).toBeNull()
  })

  it("returns null when there is no source", () => {
    expect(run_config_clone_parent_id(null)).toBeNull()
  })
})
