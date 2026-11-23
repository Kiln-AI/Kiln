import type { OptionGroup } from "$lib/ui/fancy_select_types"
import type {
  OpenEnvServer,
  NamedResetKwargs,
  RunConfigProperties,
  RunOpenEnvServer,
} from "$lib/types"
import { KilnError, createKilnError } from "$lib/utils/error_handlers"

export const OPENENV_DOCS_URL =
  "https://docs.kiln.tech/docs/evals-and-specs/openenv"
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
    placeholder: "http://127.0.0.1:8000",
  },
} as const

export const OPENENV_SERVER_URL_ERROR =
  "Enter a full URL starting with http:// or https://, like http://127.0.0.1:8000."

/**
 * The Server URL field's error, or null when the value is an http(s) URL with a
 * host. Mirrors the backend's check on OpenEnvServer.url.
 */
export function openenv_server_url_error(value: unknown): string | null {
  const text = typeof value === "string" ? value.trim() : ""
  if (!text) {
    return `"${OPENENV_SERVER_FIELDS.url.label}" is required`
  }
  // new URL() normalizes "http:host" and "http:/host" into valid URLs, which
  // the backend's urlsplit check rejects.
  if (!/^https?:\/\//i.test(text)) {
    return OPENENV_SERVER_URL_ERROR
  }
  // With an http(s):// prefix, new URL() throws when there's no host.
  try {
    new URL(text)
  } catch {
    return OPENENV_SERVER_URL_ERROR
  }
  return null
}

/** Shown wherever an OpenEnv server doesn't answer at its URL. */
export const OPENENV_UNREACHABLE_TITLE = "Can't Reach OpenEnv Server"
export const OPENENV_UNREACHABLE_STEPS = [
  "Check the OpenEnv server is running.",
  "Check the Server URL is correct.",
  "If the server is remote, check your network connection.",
]

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

// JSON with every object's keys sorted, so two argument sets that differ only
// in key order give the same string.
function canonical_json(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(
          Object.entries(v as Record<string, unknown>).sort(([a], [b]) =>
            a < b ? -1 : a > b ? 1 : 0,
          ),
        )
      : v,
  )
}

/**
 * The name of the OpenEnv server's preset whose reset arguments are exactly
 * these, or null when none is. A run stores the arguments, not the preset, so
 * this is how its sidebar names the preset it started from.
 */
export function matching_preset_name(
  openenv_server: OpenEnvServer | null,
  reset_kwargs: ResetKwargs | null | undefined,
): string | null {
  const target = canonical_json(reset_kwargs ?? {})
  const preset = openenv_server?.named_reset_kwargs?.find(
    (p) => canonical_json(p.reset_kwargs ?? {}) === target,
  )
  return preset?.name ?? null
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

/** Why a run config doesn't fit a grounded eval (see openenv_misfit). */
export type OpenEnvMisfit = "no_openenv_tools" | "other_openenv_server"

/**
 * Why a run config with these tool ids can't run the cases of an eval grounded in
 * eval_openenv_server_id, or null when it can or the eval isn't grounded. It fits when it
 * lists at least one OpenEnv tool and every OpenEnv tool it lists is served by the eval's
 * server. Matches openenv_misfit in libs/core, which the eval runner applies.
 */
export function openenv_misfit(
  eval_openenv_server_id: string | null | undefined,
  tool_ids: string[],
): OpenEnvMisfit | null {
  if (!eval_openenv_server_id) {
    return null
  }
  const openenv_tool_ids = tool_ids.filter(is_openenv_tool_id)
  if (openenv_tool_ids.length === 0) {
    return "no_openenv_tools"
  }
  const serves_all = openenv_tool_ids.every(
    (tool_id) => openenv_server_id_of_tool(tool_id) === eval_openenv_server_id,
  )
  return serves_all ? null : "other_openenv_server"
}

/** A short note on a run config that doesn't fit a grounded eval. */
export function openenv_misfit_note(
  misfit: OpenEnvMisfit,
  openenv_server_name: string,
): string {
  const what =
    misfit === "no_openenv_tools"
      ? "No OpenEnv tools."
      : "Uses another OpenEnv server."
  return `${what} This eval's cases run in ${openenv_server_name}.`
}

/** A run config Run All left out because it doesn't fit the eval's OpenEnv server. */
export type SkippedRunConfig = { id: string; name: string; reason: string }

/** The run eval stream's skipped run configs, one reason per line. */
export function skipped_run_configs_message(
  skipped_run_configs: SkippedRunConfig[],
): string {
  const count = skipped_run_configs.length
  const heading = `Skipped ${count} run config${count === 1 ? "" : "s"} that can't run this eval's cases.`
  return [
    heading,
    ...skipped_run_configs.map((skipped) => skipped.reason),
  ].join("\n")
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

export const RUN_OPTIONS_CHANGED_WHILE_SENDING =
  "The run options changed while the Environment Preset loaded. Send again."

/**
 * Reads the Environment Preset's reset arguments for `run_config_properties`.
 * The lookup can wait on the OpenEnv server, and a tool change meanwhile would
 * pair the reset arguments with another server's tools, so the send is refused
 * when the run options changed.
 */
export async function reset_kwargs_for_send(
  run_config_properties: RunConfigProperties,
  get_openenv_reset_kwargs: () => Promise<ResetKwargs | null>,
  current_run_config_properties: () => RunConfigProperties,
): Promise<ResetKwargs | null> {
  const reset_kwargs = await get_openenv_reset_kwargs()
  if (
    JSON.stringify(current_run_config_properties()) !==
    JSON.stringify(run_config_properties)
  ) {
    throw new Error(RUN_OPTIONS_CHANGED_WHILE_SENDING)
  }
  return reset_kwargs
}

/**
 * An error from a run request. The run route sends each OpenEnv refusal (no
 * session, server unreachable, reset rejected) with an `openenv_` code. Those
 * are expected and tell the user what to do, so their message is shown as
 * written, without createKilnError's "Unexpected error" prefix.
 */
export function run_request_error(e: unknown): KilnError {
  const error = createKilnError(e)
  const code = error.getCode()
  if (!code?.startsWith("openenv_")) {
    return error
  }
  const body = (e as { message?: unknown }).message
  const message =
    body && typeof body === "object" && "message" in body
      ? (body as { message: unknown }).message
      : null
  return typeof message === "string"
    ? new KilnError(message, null, code)
    : error
}
