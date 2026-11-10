import type { OptionGroup } from "$lib/ui/fancy_select_types"
import type {
  OpenEnvServer,
  NamedResetKwargs,
  RunOpenEnvServer,
} from "$lib/types"

// There's no OpenEnv docs page yet, so this links the tools docs.
export const OPENENV_DOCS_URL = "https://docs.kiln.tech/docs/tools-and-mcp"
export const SEAHAVEN_URL = "https://github.com/Kiln-AI/Seahaven"

/** Copy for the fields shared by Connect OpenEnv and the Edit OpenEnv dialog. */
export const OPENENV_SERVER_FIELDS = {
  name: { label: "Name", description: "A name to identify this OpenEnv." },
  description: {
    label: "Description",
    description: "A description of this OpenEnv for your reference.",
  },
  url: {
    label: "Server URL",
    description: "The URL of the OpenEnv server.",
    info_description:
      "Kiln connects to this server but never starts or stops it. Start the server before you connect.",
    placeholder: "http://127.0.0.1:8004",
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
  "This conversation uses an OpenEnv, so it can only continue from the latest turn."

const OPENENV_TOOL_ID_PREFIX = "kiln_tool::openenv::"

export function is_openenv_tool_id(tool_id: string): boolean {
  return tool_id.startsWith(OPENENV_TOOL_ID_PREFIX)
}

export function openenv_server_detail_link(
  project_id: string,
  openenv_server_id: string,
): string {
  return `/tools/${project_id}/openenv_servers/${openenv_server_id}`
}

/** What the run page's Environment Options field shows for the selected tools. */
export type EnvironmentFieldState =
  | { kind: "hidden" }
  | { kind: "error"; message: string }
  | { kind: "empty"; openenv_server: OpenEnvServer }
  | { kind: "options"; openenv_server: OpenEnvServer }

export function environment_field_state(
  run_openenv_server: RunOpenEnvServer,
): EnvironmentFieldState {
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
  return { kind: "options", openenv_server }
}

/** One option per Environment Option, in order, valued by its unique name. */
export function environment_option_groups(
  openenv_server: OpenEnvServer,
): OptionGroup[] {
  return [
    {
      options: (openenv_server.named_reset_kwargs ?? []).map((option) => ({
        label: option.name,
        value: option.name,
        description: format_reset_arguments(option.reset_kwargs),
        description_preformatted: true,
      })),
    },
  ]
}

/**
 * The option to select after the environment is looked up again: the same
 * name if it's still there, otherwise the first (the default), or null when
 * there are none.
 */
export function selected_option_after_change(
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
  option_name: string | null,
): ResetKwargs | null {
  const option = openenv_server.named_reset_kwargs?.find(
    (o) => o.name === option_name,
  )
  return option ? option.reset_kwargs ?? {} : null
}
