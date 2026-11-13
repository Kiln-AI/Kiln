import { describe, it, expect, vi, beforeEach } from "vitest"
import type { NamedResetKwargs } from "$lib/types"
import {
  RESET_ARGUMENTS_INVALID_JSON,
  RESET_ARGUMENTS_NOT_OBJECT,
} from "$lib/utils/openenv"

const mockGet = vi.fn()
const mockPatch = vi.fn()
const mockPost = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    PATCH: (...args: unknown[]) => mockPatch(...args),
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

import {
  blank_draft,
  clone_draft,
  compact_reset_arguments,
  draft_from,
  load_openenv_server,
  load_openenv_server_tools,
  load_openenv_server_reset_schema,
  load_openenv_server_version,
  presets_with_draft,
  presets_without,
  reset_arguments_for_form,
  reset_arguments_from_form,
  save_environment_presets,
  set_openenv_server_archived,
} from "./openenv_server_detail"
import type { JsonSchemaProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

const ACME_MANAGER: NamedResetKwargs = {
  name: "Acme Manager",
  description: "Acme's data, signed in as a manager",
  reset_kwargs: { fixture: "acme", role: "mgr" },
}
const ACME_TECH: NamedResetKwargs = {
  name: "Acme Tech",
  reset_kwargs: { fixture: "acme", role: "tech" },
}
const PRESETS = [ACME_MANAGER, ACME_TECH]

beforeEach(() => {
  mockGet.mockReset()
  mockPatch.mockReset()
  mockPost.mockReset()
})

describe("drafts", () => {
  it("starts an added preset blank", () => {
    expect(blank_draft()).toEqual({
      name: "",
      description: "",
      reset_arguments: "",
    })
  })

  it("edits a preset's name, description and formatted arguments", () => {
    expect(draft_from(ACME_MANAGER)).toEqual({
      name: "Acme Manager",
      description: "Acme's data, signed in as a manager",
      reset_arguments: '{\n  "fixture": "acme",\n  "role": "mgr"\n}',
    })
    expect(draft_from(ACME_TECH).description).toBe("")
  })

  it("clones with the same description and arguments and a (copy) name", () => {
    expect(clone_draft(ACME_MANAGER)).toEqual({
      ...draft_from(ACME_MANAGER),
      name: "Acme Manager (copy)",
    })
  })

  it("shows a preset saved without arguments as an empty object", () => {
    expect(draft_from({ name: "Beta" }).reset_arguments).toBe("{}")
  })
})

describe("presets_with_draft", () => {
  it("appends a new preset last, keeping the order", () => {
    const result = presets_with_draft(PRESETS, null, {
      name: "Acme Lead",
      description: "Acme's data, as a team lead",
      reset_arguments: '{"fixture": "acme", "role": "lead"}',
    })
    expect(result.error).toBeNull()
    expect(result.presets).toEqual([
      ACME_MANAGER,
      ACME_TECH,
      {
        name: "Acme Lead",
        description: "Acme's data, as a team lead",
        reset_kwargs: { fixture: "acme", role: "lead" },
      },
    ])
  })

  it("replaces the edited preset in place", () => {
    const result = presets_with_draft(PRESETS, 0, {
      name: "Acme Admin",
      description: "",
      reset_arguments: '{"fixture": "acme", "role": "admin"}',
    })
    expect(result.presets).toEqual([
      {
        name: "Acme Admin",
        description: null,
        reset_kwargs: { fixture: "acme", role: "admin" },
      },
      ACME_TECH,
    ])
  })

  it("trims the name and description, saving a blank description as none", () => {
    const result = presets_with_draft([], null, {
      name: "  Beta Tech ",
      description: "   ",
      reset_arguments: "{}",
    })
    expect(result.presets).toEqual([
      { name: "Beta Tech", description: null, reset_kwargs: {} },
    ])
    const described = presets_with_draft([], null, {
      name: "Beta",
      description: " Beta's data ",
      reset_arguments: "{}",
    })
    expect(described.presets?.[0].description).toBe("Beta's data")
  })

  it("saves blank arguments as an empty object", () => {
    const result = presets_with_draft([], null, {
      name: "Beta",
      description: "",
      reset_arguments: "",
    })
    expect(result.presets).toEqual([
      { name: "Beta", description: null, reset_kwargs: {} },
    ])
  })

  it.each([
    ["{not json", RESET_ARGUMENTS_INVALID_JSON],
    ['["acme", "tech"]', RESET_ARGUMENTS_NOT_OBJECT],
  ])("refuses arguments %s", (reset_arguments, error) => {
    expect(
      presets_with_draft(PRESETS, null, {
        name: "Bad",
        description: "",
        reset_arguments,
      }),
    ).toEqual({ presets: null, error })
  })

  it("doesn't change the list it was given", () => {
    const presets = [...PRESETS]
    presets_with_draft(presets, 1, {
      name: "X",
      description: "",
      reset_arguments: "{}",
    })
    expect(presets).toEqual(PRESETS)
  })
})

describe("presets_without", () => {
  it("removes only the preset at the index", () => {
    expect(presets_without(PRESETS, 0)).toEqual([ACME_TECH])
    expect(presets_without(PRESETS, 1)).toEqual([ACME_MANAGER])
  })
})

describe("compact_reset_arguments", () => {
  it("is one line of JSON", () => {
    expect(compact_reset_arguments({ fixture: "acme", user: { id: 7 } })).toBe(
      '{"fixture":"acme","user":{"id":7}}',
    )
  })

  it("shows missing arguments as an empty object", () => {
    expect(compact_reset_arguments(undefined)).toBe("{}")
  })
})

const FORM_SCHEMA: JsonSchemaProperty = {
  type: "object",
  properties: {
    company: { type: "string", enum: ["acme", "beta"] },
    user: { type: "object", properties: { id: { type: "integer" } } },
  },
}

describe("reset_arguments_for_form", () => {
  it("is an empty form for blank text", () => {
    expect(reset_arguments_for_form("  ", FORM_SCHEMA)).toEqual({
      form_value: {},
    })
  })

  it("is the parsed arguments when the form can show them", () => {
    expect(
      reset_arguments_for_form(
        '{"company": "acme", "user": {"id": 7}}',
        FORM_SCHEMA,
      ),
    ).toEqual({ form_value: { company: "acme", user: { id: 7 } } })
  })

  it.each([
    ["invalid JSON", "{", RESET_ARGUMENTS_INVALID_JSON],
    ["JSON that isn't an object", "[1]", RESET_ARGUMENTS_NOT_OBJECT],
    [
      "an unknown key",
      '{"foo": 1}',
      "The form can't show these reset arguments: unknown field 'foo'. Edit them as JSON.",
    ],
    [
      "a value the form can't hold",
      '{"user": {"id": null}}',
      "The form can't show these reset arguments: 'user.id' is null. Edit them as JSON.",
    ],
  ])("refuses %s", (_, text, error) => {
    expect(reset_arguments_for_form(text, FORM_SCHEMA)).toEqual({ error })
  })
})

describe("reset_arguments_from_form", () => {
  it("formats the form value without its empty fields", () => {
    expect(
      reset_arguments_from_form({ company: "acme", user: { id: undefined } }),
    ).toBe('{\n  "company": "acme"\n}')
  })

  it("round trips through the form", () => {
    const text = '{\n  "company": "beta",\n  "user": {\n    "id": 7\n  }\n}'
    const result = reset_arguments_for_form(text, FORM_SCHEMA)
    expect(
      "form_value" in result && reset_arguments_from_form(result.form_value),
    ).toBe(text)
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

  it("saves the whole presets list", async () => {
    mockPatch.mockResolvedValue({
      data: { name: "Acme", named_reset_kwargs: PRESETS },
      error: undefined,
    })
    await expect(
      save_environment_presets("p1", "e1", PRESETS),
    ).resolves.toEqual({ name: "Acme", named_reset_kwargs: PRESETS })
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
      { params: { path }, body: { named_reset_kwargs: PRESETS } },
    )
  })

  it("archives and unarchives", async () => {
    mockPost.mockResolvedValue({
      data: { name: "Acme", is_archived: true },
      error: undefined,
    })
    await expect(
      set_openenv_server_archived("p1", "e1", true),
    ).resolves.toEqual({ name: "Acme", is_archived: true })
    expect(mockPost).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/archive",
      { params: { path }, body: { is_archived: true } },
    )
    const error = { message: "OpenEnv server not found" }
    mockPost.mockResolvedValue({ data: undefined, error })
    await expect(set_openenv_server_archived("p1", "e1", false)).rejects.toBe(
      error,
    )
  })

  it("loads the reset schema, null when there is none", async () => {
    const reset_schema = { type: "object", properties: {} }
    mockGet.mockResolvedValueOnce({ data: { reset_schema }, error: undefined })
    await expect(load_openenv_server_reset_schema("p1", "e1")).resolves.toBe(
      reset_schema,
    )
    expect(mockGet).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/reset_schema",
      { params: { path } },
    )
    mockGet.mockResolvedValueOnce({ data: {}, error: undefined })
    await expect(load_openenv_server_reset_schema("p1", "e1")).resolves.toBe(
      null,
    )
  })

  it("throws the server's error when the reset schema can't be read", async () => {
    const error = { message: "did not answer /schema" }
    mockGet.mockResolvedValue({ data: undefined, error })
    await expect(load_openenv_server_reset_schema("p1", "e1")).rejects.toBe(
      error,
    )
  })

  it("throws the server's error when saving fails", async () => {
    const error = {
      message: "An Environment Preset named Acme Tech already exists.",
    }
    mockPatch.mockResolvedValue({ data: undefined, error })
    await expect(save_environment_presets("p1", "e1", PRESETS)).rejects.toBe(
      error,
    )
  })
})
