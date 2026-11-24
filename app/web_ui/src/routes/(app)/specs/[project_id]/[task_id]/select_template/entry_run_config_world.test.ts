import { describe, expect, it, vi, beforeEach } from "vitest"

// A plain function rather than vi.fn: this vitest reports a vi.fn's rejected
// promise as a test error even when the caller catches it.
let lookup_calls: unknown[][] = []
let lookup_impl: () => Promise<unknown> = async () => null
vi.mock("$lib/api/openenv_server_api", () => ({
  lookup_run_openenv_server: (...args: unknown[]) => {
    lookup_calls.push(args)
    return lookup_impl()
  },
}))

import { run_config_world_name } from "./entry_run_config"

beforeEach(() => {
  lookup_calls = []
})

describe("run_config_world_name", () => {
  it("names the OpenEnv server the tools reach", async () => {
    lookup_impl = async () => ({
      openenv_server: { name: "Shop" },
      error: null,
    })
    expect(await run_config_world_name("p", "t", ["tool"])).toBe("Shop")
    expect(lookup_calls).toEqual([["p", "t", ["tool"]]])
  })

  it("is null when the tools reach no server", async () => {
    lookup_impl = async () => ({ openenv_server: null, error: null })
    expect(await run_config_world_name("p", "t", ["tool"])).toBeNull()
  })

  it("skips the lookup when there are no tools", async () => {
    expect(await run_config_world_name("p", "t", [])).toBeNull()
    expect(lookup_calls).toEqual([])
  })

  it("is null when the lookup fails", async () => {
    lookup_impl = () => Promise.reject(new Error("lookup failed"))
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    expect(await run_config_world_name("p", "t", ["tool"])).toBeNull()
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })
})
