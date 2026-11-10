import { describe, it, expect, vi, beforeEach } from "vitest"
import type { NamedResetKwargs } from "$lib/types"
import {
  RESET_ARGUMENTS_INVALID_JSON,
  RESET_ARGUMENTS_NOT_OBJECT,
} from "$lib/utils/openenv"

const mockGet = vi.fn()
const mockPatch = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    PATCH: (...args: unknown[]) => mockPatch(...args),
  },
}))

import {
  blank_draft,
  clone_draft,
  draft_from,
  load_openenv_server,
  load_openenv_server_tools,
  load_openenv_server_version,
  options_with_draft,
  options_without,
  save_environment_options,
} from "./openenv_server_detail"

const ACME_MANAGER: NamedResetKwargs = {
  name: "Acme Manager",
  reset_kwargs: { fixture: "acme", role: "mgr" },
}
const ACME_TECH: NamedResetKwargs = {
  name: "Acme Tech",
  reset_kwargs: { fixture: "acme", role: "tech" },
}
const OPTIONS = [ACME_MANAGER, ACME_TECH]

beforeEach(() => {
  mockGet.mockReset()
  mockPatch.mockReset()
})

describe("drafts", () => {
  it("starts an added option blank", () => {
    expect(blank_draft()).toEqual({ name: "", reset_arguments: "" })
  })

  it("edits an option's name and formatted arguments", () => {
    expect(draft_from(ACME_TECH)).toEqual({
      name: "Acme Tech",
      reset_arguments: '{\n  "fixture": "acme",\n  "role": "tech"\n}',
    })
  })

  it("clones with the same arguments and a (copy) name", () => {
    expect(clone_draft(ACME_TECH)).toEqual({
      name: "Acme Tech (copy)",
      reset_arguments: draft_from(ACME_TECH).reset_arguments,
    })
  })

  it("shows an option saved without arguments as an empty object", () => {
    expect(draft_from({ name: "Beta" }).reset_arguments).toBe("{}")
  })
})

describe("options_with_draft", () => {
  it("appends a new option last, keeping the order", () => {
    const result = options_with_draft(OPTIONS, null, {
      name: "Acme Lead",
      reset_arguments: '{"fixture": "acme", "role": "lead"}',
    })
    expect(result.error).toBeNull()
    expect(result.options).toEqual([
      ACME_MANAGER,
      ACME_TECH,
      { name: "Acme Lead", reset_kwargs: { fixture: "acme", role: "lead" } },
    ])
  })

  it("replaces the edited option in place", () => {
    const result = options_with_draft(OPTIONS, 0, {
      name: "Acme Admin",
      reset_arguments: '{"fixture": "acme", "role": "admin"}',
    })
    expect(result.options).toEqual([
      { name: "Acme Admin", reset_kwargs: { fixture: "acme", role: "admin" } },
      ACME_TECH,
    ])
  })

  it("trims the name", () => {
    const result = options_with_draft([], null, {
      name: "  Beta Tech ",
      reset_arguments: "{}",
    })
    expect(result.options).toEqual([{ name: "Beta Tech", reset_kwargs: {} }])
  })

  it("saves blank arguments as an empty object", () => {
    const result = options_with_draft([], null, {
      name: "Beta",
      reset_arguments: "",
    })
    expect(result.options).toEqual([{ name: "Beta", reset_kwargs: {} }])
  })

  it.each([
    ["{not json", RESET_ARGUMENTS_INVALID_JSON],
    ['["acme", "tech"]', RESET_ARGUMENTS_NOT_OBJECT],
  ])("refuses arguments %s", (reset_arguments, error) => {
    expect(
      options_with_draft(OPTIONS, null, { name: "Bad", reset_arguments }),
    ).toEqual({ options: null, error })
  })

  it("doesn't change the list it was given", () => {
    const options = [...OPTIONS]
    options_with_draft(options, 1, { name: "X", reset_arguments: "{}" })
    expect(options).toEqual(OPTIONS)
  })
})

describe("options_without", () => {
  it("removes only the option at the index", () => {
    expect(options_without(OPTIONS, 0)).toEqual([ACME_TECH])
    expect(options_without(OPTIONS, 1)).toEqual([ACME_MANAGER])
  })
})

describe("API calls", () => {
  const path = { project_id: "p1", openenv_server_id: "e1" }

  it("loads the environment", async () => {
    mockGet.mockResolvedValue({ data: { name: "Acme" }, error: undefined })
    await expect(load_openenv_server("p1", "e1")).resolves.toEqual({
      name: "Acme",
    })
    expect(mockGet).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
      { params: { path } },
    )
  })

  it("loads the tools", async () => {
    mockGet.mockResolvedValue({
      data: [{ name: "list_items" }],
      error: undefined,
    })
    await expect(load_openenv_server_tools("p1", "e1")).resolves.toEqual([
      { name: "list_items" },
    ])
    expect(mockGet).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/tools",
      { params: { path } },
    )
  })

  it("loads the version", async () => {
    mockGet.mockResolvedValue({
      data: { openenv_version: "acme-env@0.3.1" },
      error: undefined,
    })
    await expect(load_openenv_server_version("p1", "e1")).resolves.toBe(
      "acme-env@0.3.1",
    )
    expect(mockGet).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/version",
      { params: { path } },
    )
  })

  it.each([
    ["environment", () => load_openenv_server("p1", "e1")],
    ["tools", () => load_openenv_server_tools("p1", "e1")],
    ["version", () => load_openenv_server_version("p1", "e1")],
  ])("throws the server's error when loading the %s fails", async (_, load) => {
    const error = { message: "Can't reach it" }
    mockGet.mockResolvedValue({ data: undefined, error })
    await expect(load()).rejects.toBe(error)
  })

  it("saves the whole options list", async () => {
    mockPatch.mockResolvedValue({
      data: { name: "Acme", named_reset_kwargs: OPTIONS },
      error: undefined,
    })
    await expect(
      save_environment_options("p1", "e1", OPTIONS),
    ).resolves.toEqual({ name: "Acme", named_reset_kwargs: OPTIONS })
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
      { params: { path }, body: { named_reset_kwargs: OPTIONS } },
    )
  })

  it("throws the server's error when saving fails", async () => {
    const error = {
      message: "An Environment Option named Acme Tech already exists.",
    }
    mockPatch.mockResolvedValue({ data: undefined, error })
    await expect(save_environment_options("p1", "e1", OPTIONS)).rejects.toBe(
      error,
    )
  })
})
