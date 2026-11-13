import { describe, it, expect } from "vitest"
import type { OpenEnvServer } from "$lib/types"
import {
  RESET_ARGUMENTS_INVALID_JSON,
  RESET_ARGUMENTS_NOT_OBJECT,
  OPENENV_SERVER_URL_ERROR,
  openenv_server_detail_link,
  openenv_server_url_error,
  environment_preset_field_state,
  environment_preset_groups,
  format_reset_arguments,
  openenv_tool_name,
  is_openenv_tool_id,
  keeps_unlisted_openenv_tool,
  openenv_server_id_of_tool,
  parse_reset_arguments,
  reset_kwargs_for,
  selected_preset_after_change,
} from "./openenv"

describe("openenv_server_url_error", () => {
  it.each([
    "http://127.0.0.1:8000",
    "https://env.example.com/openenv",
    "  http://localhost:8000  ",
  ])("accepts %s", (url) => {
    expect(openenv_server_url_error(url)).toBeNull()
  })

  it.each([
    "127.0.0.1:8000",
    "ftp://example.com",
    "http://",
    "not a url",
    "http:example.com",
    "http:/host",
  ])("refuses %s", (url) => {
    expect(openenv_server_url_error(url)).toBe(OPENENV_SERVER_URL_ERROR)
  })

  it.each(["", "   ", null, undefined])("requires a value: %s", (url) => {
    expect(openenv_server_url_error(url)).toBe('"Server URL" is required')
  })

  it("gives an example URL on the default Seahaven port", () => {
    expect(OPENENV_SERVER_URL_ERROR).toBe(
      "Enter a full URL starting with http:// or https://, like http://127.0.0.1:8000.",
    )
  })
})

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
  is_archived: false,
  url: "http://127.0.0.1:8004",
  named_reset_kwargs: [
    {
      name: "Acme Tech",
      description: "  Acme's data, as a technician  ",
      reset_kwargs: { company: "acme", role: "tech" },
    },
    {
      name: "Acme Manager",
      reset_kwargs: { company: "acme", role: "manager" },
    },
  ],
}

const BARE: OpenEnvServer = {
  id: "openenv_2",
  name: "Beta",
  is_archived: false,
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

describe("openenv_server_id_of_tool", () => {
  it("takes the server id from an OpenEnv tool id", () => {
    expect(
      openenv_server_id_of_tool("kiln_tool::openenv::openenv_1::list_items"),
    ).toBe("openenv_1")
  })

  it("is null for other or malformed tool ids", () => {
    expect(openenv_server_id_of_tool("mcp::remote::s::search")).toBeNull()
    expect(openenv_server_id_of_tool("kiln_tool::openenv::::list")).toBeNull()
  })
})

describe("keeps_unlisted_openenv_tool", () => {
  const archived = new Set(["openenv_2"])

  it("keeps an offline server's tool", () => {
    expect(
      keeps_unlisted_openenv_tool(
        "kiln_tool::openenv::openenv_1::list_items",
        archived,
      ),
    ).toBe(true)
  })

  it("drops an archived server's tool", () => {
    expect(
      keeps_unlisted_openenv_tool(
        "kiln_tool::openenv::openenv_2::list_items",
        archived,
      ),
    ).toBe(false)
  })

  it("drops anything that isn't an OpenEnv tool", () => {
    expect(
      keeps_unlisted_openenv_tool("mcp::remote::s::search", archived),
    ).toBe(false)
  })
})

describe("openenv_server_detail_link", () => {
  it("links the OpenEnv detail page", () => {
    expect(openenv_server_detail_link("p1", "openenv_1")).toBe(
      "/tools/p1/openenv_servers/openenv_1",
    )
  })
})

describe("environment_preset_field_state", () => {
  it("is hidden when the tools reach no OpenEnv", () => {
    expect(
      environment_preset_field_state({ openenv_server: null, error: null }),
    ).toEqual({
      kind: "hidden",
    })
  })

  it("shows the error when the tools can't run", () => {
    const message =
      "Your tools use more than one OpenEnv (Acme, Beta). A run can only use one."
    expect(
      environment_preset_field_state({ openenv_server: null, error: message }),
    ).toEqual({
      kind: "error",
      message,
    })
  })

  it("is empty for an OpenEnv server with no Environment Presets", () => {
    expect(environment_preset_field_state({ openenv_server: BARE })).toEqual({
      kind: "empty",
      openenv_server: BARE,
    })
    const no_list: OpenEnvServer = {
      id: "openenv_3",
      name: "Gamma",
      is_archived: false,
    }
    expect(
      environment_preset_field_state({ openenv_server: no_list }).kind,
    ).toBe("empty")
  })

  it("lists the presets otherwise", () => {
    expect(environment_preset_field_state({ openenv_server: ACME })).toEqual({
      kind: "presets",
      openenv_server: ACME,
    })
  })
})

describe("environment_preset_groups", () => {
  it("lists presets in order, described by their own description", () => {
    const [group] = environment_preset_groups(ACME)
    expect(group.options).toEqual([
      {
        label: "Acme Tech",
        value: "Acme Tech",
        description: "Acme's data, as a technician",
      },
      { label: "Acme Manager", value: "Acme Manager", description: undefined },
    ])
  })

  it("shows no description for a blank one", () => {
    const env: OpenEnvServer = {
      id: "openenv_5",
      name: "Beta",
      is_archived: false,
      named_reset_kwargs: [{ name: "Blank", description: "   " }],
    }
    expect(environment_preset_groups(env)[0].options[0].description).toBe(
      undefined,
    )
  })
})

describe("selected_preset_after_change", () => {
  it("keeps a name that still exists", () => {
    expect(selected_preset_after_change(ACME, "Acme Manager")).toBe(
      "Acme Manager",
    )
  })

  it("falls back to the first preset", () => {
    expect(selected_preset_after_change(ACME, null)).toBe("Acme Tech")
    expect(selected_preset_after_change(ACME, "Removed")).toBe("Acme Tech")
  })

  it("is null with no presets", () => {
    expect(selected_preset_after_change(BARE, "Acme Tech")).toBeNull()
  })
})

describe("reset_kwargs_for", () => {
  it("returns the named preset's reset arguments", () => {
    expect(reset_kwargs_for(ACME, "Acme Manager")).toEqual({
      company: "acme",
      role: "manager",
    })
  })

  it("is null for an unknown or missing name", () => {
    expect(reset_kwargs_for(ACME, "Removed")).toBeNull()
    expect(reset_kwargs_for(ACME, null)).toBeNull()
  })

  it("treats a preset without arguments as an empty object", () => {
    const env: OpenEnvServer = {
      id: "openenv_4",
      name: "Delta",
      is_archived: false,
      named_reset_kwargs: [{ name: "Default" }],
    }
    expect(reset_kwargs_for(env, "Default")).toEqual({})
  })
})
