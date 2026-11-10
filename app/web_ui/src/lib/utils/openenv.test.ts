import { describe, it, expect } from "vitest"
import type { OpenEnvServer } from "$lib/types"
import {
  RESET_ARGUMENTS_INVALID_JSON,
  RESET_ARGUMENTS_NOT_OBJECT,
  openenv_server_detail_link,
  environment_field_state,
  environment_option_groups,
  format_reset_arguments,
  openenv_tool_name,
  is_openenv_tool_id,
  parse_reset_arguments,
  reset_kwargs_for,
  selected_option_after_change,
} from "./openenv"

describe("format_reset_arguments", () => {
  it("formats over several lines with a 2-space indent", () => {
    expect(format_reset_arguments({ fixture: "acme", user: { id: 7 } })).toBe(
      '{\n  "fixture": "acme",\n  "user": {\n    "id": 7\n  }\n}',
    )
  })

  it("shows missing arguments as an empty object", () => {
    expect(format_reset_arguments(undefined)).toBe("{}")
    expect(format_reset_arguments(null)).toBe("{}")
    expect(format_reset_arguments({})).toBe("{}")
  })
})

describe("parse_reset_arguments", () => {
  it("parses a JSON object", () => {
    expect(parse_reset_arguments('{"fixture": "acme", "seed": 3}')).toEqual({
      reset_kwargs: { fixture: "acme", seed: 3 },
      error: null,
    })
  })

  it("treats an empty object and blank text as no arguments", () => {
    expect(parse_reset_arguments("{}")).toEqual({
      reset_kwargs: {},
      error: null,
    })
    expect(parse_reset_arguments("  \n ")).toEqual({
      reset_kwargs: {},
      error: null,
    })
  })

  it("rejects invalid JSON", () => {
    expect(parse_reset_arguments('{"fixture": ')).toEqual({
      reset_kwargs: null,
      error: RESET_ARGUMENTS_INVALID_JSON,
    })
  })

  it.each(['["acme", "tech"]', '"acme"', "3", "null", "true"])(
    "rejects JSON that isn't an object: %s",
    (text) => {
      expect(parse_reset_arguments(text)).toEqual({
        reset_kwargs: null,
        error: RESET_ARGUMENTS_NOT_OBJECT,
      })
    },
  )

  it("round-trips formatted arguments", () => {
    const kwargs = { fixture: "beta", role: "tech", flags: [1, 2] }
    expect(parse_reset_arguments(format_reset_arguments(kwargs))).toEqual({
      reset_kwargs: kwargs,
      error: null,
    })
  })
})

const ACME: OpenEnvServer = {
  id: "openenv_1",
  name: "Acme",
  url: "http://127.0.0.1:8004",
  named_reset_kwargs: [
    { name: "Acme Tech", reset_kwargs: { company: "acme", role: "tech" } },
    {
      name: "Acme Manager",
      reset_kwargs: { company: "acme", role: "manager" },
    },
  ],
}

const BARE: OpenEnvServer = {
  id: "openenv_2",
  name: "Beta",
  named_reset_kwargs: [],
}

describe("is_openenv_tool_id", () => {
  it("matches only OpenEnv tool ids", () => {
    expect(
      is_openenv_tool_id("kiln_tool::openenv::openenv_1::list_items"),
    ).toBe(true)
    expect(is_openenv_tool_id("mcp::remote::server::search")).toBe(false)
    expect(is_openenv_tool_id("kiln_tool::add_numbers")).toBe(false)
  })
})

describe("openenv_tool_name", () => {
  it("takes the tool name from an OpenEnv tool id", () => {
    expect(openenv_tool_name("kiln_tool::openenv::openenv_1::list_items")).toBe(
      "list_items",
    )
  })

  it("is null for other tool ids", () => {
    expect(openenv_tool_name("mcp::remote::server::search")).toBe(null)
    expect(openenv_tool_name("kiln_tool::add_numbers")).toBe(null)
  })

  it("is null for a malformed OpenEnv tool id", () => {
    expect(openenv_tool_name("kiln_tool::openenv::openenv_1")).toBe(null)
    expect(openenv_tool_name("kiln_tool::openenv::openenv_1::")).toBe(null)
    expect(openenv_tool_name("kiln_tool::openenv::::list_items")).toBe(null)
    expect(openenv_tool_name("kiln_tool::openenv::openenv_1::a::b")).toBe(null)
  })
})

describe("openenv_server_detail_link", () => {
  it("links the OpenEnv detail page", () => {
    expect(openenv_server_detail_link("p1", "openenv_1")).toBe(
      "/tools/p1/openenv_servers/openenv_1",
    )
  })
})

describe("environment_field_state", () => {
  it("is hidden when the tools reach no OpenEnv", () => {
    expect(
      environment_field_state({ openenv_server: null, error: null }),
    ).toEqual({
      kind: "hidden",
    })
  })

  it("shows the error when the tools can't run", () => {
    const message =
      "Your tools use more than one OpenEnv (Acme, Beta). A run can only use one."
    expect(
      environment_field_state({ openenv_server: null, error: message }),
    ).toEqual({
      kind: "error",
      message,
    })
  })

  it("is empty for an OpenEnv with no Environment Options", () => {
    expect(environment_field_state({ openenv_server: BARE })).toEqual({
      kind: "empty",
      openenv_server: BARE,
    })
    const no_list: OpenEnvServer = { id: "openenv_3", name: "Gamma" }
    expect(environment_field_state({ openenv_server: no_list }).kind).toBe(
      "empty",
    )
  })

  it("lists the options otherwise", () => {
    expect(environment_field_state({ openenv_server: ACME })).toEqual({
      kind: "options",
      openenv_server: ACME,
    })
  })
})

describe("environment_option_groups", () => {
  it("lists options in order with their reset arguments as preformatted JSON", () => {
    const [group] = environment_option_groups(ACME)
    expect(group.options.map((o) => o.value)).toEqual([
      "Acme Tech",
      "Acme Manager",
    ])
    expect(group.options[0]).toEqual({
      label: "Acme Tech",
      value: "Acme Tech",
      description: '{\n  "company": "acme",\n  "role": "tech"\n}',
      description_preformatted: true,
    })
  })
})

describe("selected_option_after_change", () => {
  it("keeps a name that still exists", () => {
    expect(selected_option_after_change(ACME, "Acme Manager")).toBe(
      "Acme Manager",
    )
  })

  it("falls back to the first option", () => {
    expect(selected_option_after_change(ACME, null)).toBe("Acme Tech")
    expect(selected_option_after_change(ACME, "Removed")).toBe("Acme Tech")
  })

  it("is null with no options", () => {
    expect(selected_option_after_change(BARE, "Acme Tech")).toBeNull()
  })
})

describe("reset_kwargs_for", () => {
  it("returns the named option's reset arguments", () => {
    expect(reset_kwargs_for(ACME, "Acme Manager")).toEqual({
      company: "acme",
      role: "manager",
    })
  })

  it("is null for an unknown or missing name", () => {
    expect(reset_kwargs_for(ACME, "Removed")).toBeNull()
    expect(reset_kwargs_for(ACME, null)).toBeNull()
  })

  it("treats an option without arguments as an empty object", () => {
    const env: OpenEnvServer = {
      id: "openenv_4",
      name: "Delta",
      named_reset_kwargs: [{ name: "Default" }],
    }
    expect(reset_kwargs_for(env, "Default")).toEqual({})
  })
})
