import { client } from "$lib/api_client"
import type { OpenEnvServer, OpenEnvTool, NamedResetKwargs } from "$lib/types"
import {
  format_reset_arguments,
  parse_reset_arguments,
} from "$lib/utils/openenv"

export async function load_openenv_server(
  project_id: string,
  openenv_server_id: string,
): Promise<OpenEnvServer> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
    { params: { path: { project_id, openenv_server_id } } },
  )
  if (error) {
    throw error
  }
  return data
}

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

export function options_without(
  options: NamedResetKwargs[],
  index: number,
): NamedResetKwargs[] {
  return options.filter((_, i) => i !== index)
}
