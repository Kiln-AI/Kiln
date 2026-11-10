import { describe, it, expect, vi } from "vitest"
import type { RunConfigProperties } from "$lib/types"
import { build_run_request } from "./run_request"

const AGENT_CONFIG = {
  type: "kiln_agent",
  model_name: "gpt-4o",
  model_provider_name: "openai",
  prompt_id: "simple_prompt_builder",
  temperature: 1,
  top_p: 1,
  structured_output_mode: "default",
  thinking_level: null,
  tools_config: { tools: ["kiln_tool::openenv::openenv_1::list_items"] },
} as unknown as RunConfigProperties

const MCP_CONFIG = {
  type: "mcp",
  tool_reference: { tool_server_id: "s1", tool_name: "search" },
} as unknown as RunConfigProperties

function args(
  run_config_properties: RunConfigProperties,
  kwargs: Record<string, unknown> | null,
) {
  return {
    run_config_properties,
    plaintext_input: "Triage ticket 4821",
    structured_input: null,
    task_run_config_id: "rc_1",
    get_openenv_reset_kwargs: vi.fn().mockResolvedValue(kwargs),
  }
}

describe("build_run_request", () => {
  it("includes the chosen reset arguments", async () => {
    const body = await build_run_request(
      args(AGENT_CONFIG, { company: "acme" }),
    )
    expect(body).toEqual({
      run_config_properties: AGENT_CONFIG,
      plaintext_input: "Triage ticket 4821",
      structured_input: null,
      tags: ["manual_run"],
      task_run_config_id: "rc_1",
      openenv_reset_kwargs: { company: "acme" },
    })
  })

  it("leaves them out when the tools reach no OpenEnv", async () => {
    const body = await build_run_request(args(AGENT_CONFIG, null))
    expect("openenv_reset_kwargs" in body).toBe(false)
  })

  it("never asks for them for an MCP run config", async () => {
    const request_args = args(MCP_CONFIG, { company: "acme" })
    const body = await build_run_request(request_args)
    expect("openenv_reset_kwargs" in body).toBe(false)
    expect(request_args.get_openenv_reset_kwargs).not.toHaveBeenCalled()
  })

  it("passes on a refusal from the Environment Options field", async () => {
    const request_args = args(AGENT_CONFIG, null)
    request_args.get_openenv_reset_kwargs.mockRejectedValue(
      new Error("Network down"),
    )
    await expect(build_run_request(request_args)).rejects.toThrow(
      "Network down",
    )
  })
})
