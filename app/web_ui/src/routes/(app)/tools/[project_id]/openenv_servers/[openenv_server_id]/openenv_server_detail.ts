import { client } from "$lib/api_client"
import type { OpenEnvServer, OpenEnvTool, NamedResetKwargs } from "$lib/types"
import {
  format_reset_arguments,
  parse_reset_arguments,
  type ResetKwargs,
} from "$lib/utils/openenv"
import {
  form_value_to_kwargs,
  kwargs_fit_form,
} from "$lib/utils/openenv_reset_schema"
import type { JsonSchemaProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

export {
  load_openenv_server,
  load_openenv_server_reset_schema,
} from "$lib/api/openenv_server_api"

export async function load_openenv_server_tools(
  project_id: string,
  openenv_server_id: string,
): Promise<OpenEnvTool[]> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/tools",
    { params: { path: { project_id, openenv_server_id } } },
  )
  if (error) {
    throw error
  }
  return data
}

export async function load_openenv_server_version(
  project_id: string,
  openenv_server_id: string,
): Promise<string> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/version",
    { params: { path: { project_id, openenv_server_id } } },
  )
  if (error) {
    throw error
  }
  return data.openenv_version
}

/** Archive or unarchive the OpenEnv server. */
export async function set_openenv_server_archived(
  project_id: string,
  openenv_server_id: string,
  is_archived: boolean,
): Promise<OpenEnvServer> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/archive",
    {
      params: { path: { project_id, openenv_server_id } },
      body: { is_archived },
    },
  )
  if (error) {
    throw error
  }
  return data
}

/** PATCH the whole Environment Presets list; the server replaces it. */
export async function save_environment_presets(
  project_id: string,
  openenv_server_id: string,
  presets: NamedResetKwargs[],
): Promise<OpenEnvServer> {
  const { data, error } = await client.PATCH(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
    {
      params: { path: { project_id, openenv_server_id } },
      body: { named_reset_kwargs: presets },
    },
  )
  if (error) {
    throw error
  }
  return data
}

/** What the Environment Preset dialog edits: its fields and the editor's text. */
export type PresetDraft = {
  name: string
  description: string
  reset_arguments: string
}

export function blank_draft(): PresetDraft {
  return { name: "", description: "", reset_arguments: "" }
}

export function draft_from(preset: NamedResetKwargs): PresetDraft {
  return {
    name: preset.name,
    description: preset.description ?? "",
    reset_arguments: format_reset_arguments(preset.reset_kwargs),
  }
}

export function clone_draft(preset: NamedResetKwargs): PresetDraft {
  return { ...draft_from(preset), name: `${preset.name} (copy)` }
}

export type DraftResult =
  | { presets: NamedResetKwargs[]; error: null }
  | { presets: null; error: string }

/**
 * The list to save after the dialog's Save: the draft replaces the preset at
 * `editing_index`, or is appended when it's null. Returns the error to show
 * instead when the Reset Arguments aren't a JSON object.
 */
export function presets_with_draft(
  presets: NamedResetKwargs[],
  editing_index: number | null,
  draft: PresetDraft,
): DraftResult {
  const parsed = parse_reset_arguments(draft.reset_arguments)
  if (parsed.error !== null) {
    return { presets: null, error: parsed.error }
  }
  const preset: NamedResetKwargs = {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    reset_kwargs: parsed.reset_kwargs,
  }
  if (editing_index === null) {
    return { presets: [...presets, preset], error: null }
  }
  return {
    presets: presets.map((existing, i) =>
      i === editing_index ? preset : existing,
    ),
    error: null,
  }
}

/** Reset arguments on one line, for a table cell that expands to the full JSON. */
export function compact_reset_arguments(
  reset_kwargs: ResetKwargs | null | undefined,
): string {
  return JSON.stringify(reset_kwargs ?? {})
}

export const RESET_ARGUMENTS_DESCRIPTION =
  "Passed to the OpenEnv server's reset(). Which keys exist depends on the server."
export const RESET_ARGUMENTS_SCHEMA_DESCRIPTION =
  "From the OpenEnv server's reset schema. Leave a field empty to use the server's default."

export type FormSwitch = { form_value: ResetKwargs } | { error: string }

/**
 * The value to show in the reset schema form for the Reset Arguments editor's
 * text, or why the form can't show it.
 */
export function reset_arguments_for_form(
  text: string,
  form_schema: JsonSchemaProperty,
): FormSwitch {
  const parsed = parse_reset_arguments(text)
  if (parsed.error !== null) {
    return { error: parsed.error }
  }
  const fit = kwargs_fit_form(parsed.reset_kwargs, form_schema)
  if (!fit.fits) {
    return {
      error: `The form can't show these reset arguments: ${fit.reason}. Edit them as JSON.`,
    }
  }
  return { form_value: parsed.reset_kwargs }
}

/** The Reset Arguments editor's text for a value read from the form. */
export function reset_arguments_from_form(form_value: unknown): string {
  return format_reset_arguments(form_value_to_kwargs(form_value) as ResetKwargs)
}

export function presets_without(
  presets: NamedResetKwargs[],
  index: number,
): NamedResetKwargs[] {
  return presets.filter((_, i) => i !== index)
}
