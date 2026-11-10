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

/** PATCH the whole Environment Options list; the server replaces it. */
export async function save_environment_options(
  project_id: string,
  openenv_server_id: string,
  options: NamedResetKwargs[],
): Promise<OpenEnvServer> {
  const { data, error } = await client.PATCH(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
    {
      params: { path: { project_id, openenv_server_id } },
      body: { named_reset_kwargs: options },
    },
  )
  if (error) {
    throw error
  }
  return data
}

/** What the Environment Option dialog edits: the name and the editor's text. */
export type OptionDraft = {
  name: string
  reset_arguments: string
}

export function blank_draft(): OptionDraft {
  return { name: "", reset_arguments: "" }
}

export function draft_from(option: NamedResetKwargs): OptionDraft {
  return {
    name: option.name,
    reset_arguments: format_reset_arguments(option.reset_kwargs),
  }
}

export function clone_draft(option: NamedResetKwargs): OptionDraft {
  return { ...draft_from(option), name: `${option.name} (copy)` }
}

export type DraftResult =
  | { options: NamedResetKwargs[]; error: null }
  | { options: null; error: string }

/**
 * The list to save after the dialog's Save: the draft replaces the option at
 * `editing_index`, or is appended when it's null. Returns the error to show
 * instead when the Reset Arguments aren't a JSON object.
 */
export function options_with_draft(
  options: NamedResetKwargs[],
  editing_index: number | null,
  draft: OptionDraft,
): DraftResult {
  const parsed = parse_reset_arguments(draft.reset_arguments)
  if (parsed.error !== null) {
    return { options: null, error: parsed.error }
  }
  const option: NamedResetKwargs = {
    name: draft.name.trim(),
    reset_kwargs: parsed.reset_kwargs,
  }
  if (editing_index === null) {
    return { options: [...options, option], error: null }
  }
  return {
    options: options.map((existing, i) =>
      i === editing_index ? option : existing,
    ),
    error: null,
  }
}

export const RESET_ARGUMENTS_DESCRIPTION =
  "Passed to the OpenEnv's reset(). Which keys exist depends on the server."
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

export function options_without(
  options: NamedResetKwargs[],
  index: number,
): NamedResetKwargs[] {
  return options.filter((_, i) => i !== index)
}
