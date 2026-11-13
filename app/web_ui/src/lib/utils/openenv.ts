import type { OptionGroup } from "$lib/ui/fancy_select_types"
import type {
  OpenEnvServer,
  NamedResetKwargs,
  RunOpenEnvServer,
} from "$lib/types"

// There's no OpenEnv docs page yet, so this links the tools docs.
export const OPENENV_DOCS_URL = "https://docs.kiln.tech/docs/tools-and-mcp"
export const SEAHAVEN_URL = "https://github.com/Kiln-AI/Seahaven"

/**
 * Copy for the fields shared by Connect OpenEnv Server and its Edit dialog. It
 * matches the MCP server connect form's.
 */
export const OPENENV_SERVER_FIELDS = {
  name: {
    label: "Name",
    description: "A name to identify this OpenEnv server.",
  },
  description: {
    label: "Description",
    description: "A description of this OpenEnv server for your reference.",
  },
  url: {
    label: "Server URL",
    description: "The URL of the OpenEnv server.",
    placeholder: "https://example.com/openenv",
  },
} as const

export type ResetKwargs = NonNullable<NamedResetKwargs["reset_kwargs"]>

export const RESET_ARGUMENTS_INVALID_JSON =
  "Reset arguments must be valid JSON."
export const RESET_ARGUMENTS_NOT_OBJECT =
  "Reset arguments must be a JSON object."

export function format_reset_arguments(
  reset_kwargs: ResetKwargs | null | undefined,
): string {
  return JSON.stringify(reset_kwargs ?? {}, null, 2)
}

export type ParsedResetArguments =
  | { reset_kwargs: ResetKwargs; error: null }
  | { reset_kwargs: null; error: string }

/** Parse the Reset Arguments editor's text. Blank text is an empty object. */
export function parse_reset_arguments(text: string): ParsedResetArguments {
  if (!text.trim()) {
    return { reset_kwargs: {}, error: null }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { reset_kwargs: null, error: RESET_ARGUMENTS_INVALID_JSON }
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { reset_kwargs: null, error: RESET_ARGUMENTS_NOT_OBJECT }
  }
  return { reset_kwargs: parsed as ResetKwargs, error: null }
}

export const FORK_DISABLED_WITH_OPENENV =
  "This conversation uses an OpenEnv server, so it can only continue from the latest turn."

const OPENENV_TOOL_ID_PREFIX = "kiln_tool::openenv::"

export function is_openenv_tool_id(tool_id: string): boolean {
  return tool_id.startsWith(OPENENV_TOOL_ID_PREFIX)
}

/**
 * The tool name in an OpenEnv tool id (kiln_tool::openenv::<openenv_server_id>::<tool_name>),
 * or null when the id isn't a well-formed one. Matches openenv_and_tool_name_from_id in
 * libs/core. An offline OpenEnv is missing from available_tools, so its tools are
 * named from their ids.
 */
export function openenv_tool_name(tool_id: string): string | null {
  if (!is_openenv_tool_id(tool_id)) {
    return null
  }
  const parts = tool_id.split("::")
  if (parts.length !== 4 || !parts[2] || !parts[3]) {
    return null
  }
  return parts[3]
}

/** The OpenEnv server id in an OpenEnv tool id, or null when it isn't one. */
export function openenv_server_id_of_tool(tool_id: string): string | null {
  if (openenv_tool_name(tool_id) === null) {
    return null
  }
  return tool_id.split("::")[2]
}

/**
 * Whether a picker keeps a selected OpenEnv tool that available_tools doesn't
 * list. An offline server's tools stay selected, so the run reports the server
 * can't be reached. An archived server's tools are dropped, as an archived MCP
 * server's are.
 */
export function keeps_unlisted_openenv_tool(
  tool_id: string,
  archived_openenv_server_ids: Set<string>,
): boolean {
  const openenv_server_id = openenv_server_id_of_tool(tool_id)
  return (
    openenv_server_id !== null &&
    !archived_openenv_server_ids.has(openenv_server_id)
  )
}

export function openenv_server_detail_link(
  project_id: string,
  openenv_server_id: string,
): string {
  return `/tools/${project_id}/openenv_servers/${openenv_server_id}`
}

/** What the run page's Environment Preset field shows for the selected tools. */
export type EnvironmentPresetFieldState =
  | { kind: "hidden" }
  | { kind: "error"; message: string }
  | { kind: "empty"; openenv_server: OpenEnvServer }
  | { kind: "presets"; openenv_server: OpenEnvServer }

export function environment_preset_field_state(
  run_openenv_server: RunOpenEnvServer,
): EnvironmentPresetFieldState {
  if (run_openenv_server.error) {
    return { kind: "error", message: run_openenv_server.error }
  }
  const openenv_server = run_openenv_server.openenv_server
  if (!openenv_server) {
    return { kind: "hidden" }
  }
  if (!openenv_server.named_reset_kwargs?.length) {
    return { kind: "empty", openenv_server }
  }
  return { kind: "presets", openenv_server }
}

/**
 * One option per Environment Preset, in order, valued by its unique name and
 * described by the preset's own description.
 */
export function environment_preset_groups(
  openenv_server: OpenEnvServer,
): OptionGroup[] {
  return [
    {
      options: (openenv_server.named_reset_kwargs ?? []).map((preset) => ({
        label: preset.name,
        value: preset.name,
        description: preset.description?.trim() || undefined,
      })),
    },
  ]
}

/**
 * The preset to select after the environment is looked up again: the same
 * name if it's still there, otherwise the first (the default), or null when
 * there are none.
 */
export function selected_preset_after_change(
  openenv_server: OpenEnvServer,
  previous_name: string | null,
): string | null {
  const names = (openenv_server.named_reset_kwargs ?? []).map((o) => o.name)
  if (previous_name !== null && names.includes(previous_name)) {
    return previous_name
  }
  return names[0] ?? null
}

export function reset_kwargs_for(
  openenv_server: OpenEnvServer,
  preset_name: string | null,
): ResetKwargs | null {
  const preset = openenv_server.named_reset_kwargs?.find(
    (p) => p.name === preset_name,
  )
  return preset ? preset.reset_kwargs ?? {} : null
}
