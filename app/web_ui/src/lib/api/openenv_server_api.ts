import { client } from "$lib/api_client"
import type { OpenEnvServer, RunOpenEnvServer } from "$lib/types"
import { KilnError, createKilnError } from "$lib/utils/error_handlers"

/** The KilnError code for a save refused because no OpenEnv server answered. */
export const OPENENV_UNREACHABLE_CODE = "openenv_unreachable"

/**
 * An error from the OpenEnv server routes, keeping the backend's message as it
 * is. Their 400s and 502s (a bad field, a server that doesn't answer) are
 * expected, so they don't take createKilnError's "Unexpected error" prefix.
 */
export function openenv_server_error(
  e: unknown,
  code: string | null = null,
): KilnError {
  if (e instanceof KilnError) {
    return e
  }
  if (
    e &&
    typeof e === "object" &&
    "message" in e &&
    typeof e.message === "string" &&
    e.message
  ) {
    return new KilnError(e.message, null, code)
  }
  return createKilnError(e)
}

/** Whether a save failed because no OpenEnv server answered at the URL. */
export function is_openenv_unreachable(error: KilnError | null): boolean {
  return error?.getCode() === OPENENV_UNREACHABLE_CODE
}

// The create and update routes answer 502 when the URL's server doesn't
// answer, and 400 for an invalid field.
function save_error(error: unknown, response: Response): KilnError {
  return openenv_server_error(
    error,
    response.status === 502 ? OPENENV_UNREACHABLE_CODE : null,
  )
}

export type OpenEnvServerFields = {
  name: string
  description: string | null
  url: string
}

/** Connect an OpenEnv server. Throws openenv_server_error's KilnError. */
export async function create_openenv_server(
  project_id: string,
  fields: OpenEnvServerFields,
): Promise<OpenEnvServer> {
  const { data, error, response } = await client.POST(
    "/api/projects/{project_id}/openenv_servers",
    { params: { path: { project_id } }, body: fields },
  )
  if (error) {
    throw save_error(error, response)
  }
  return data
}

/**
 * Save the Edit dialog's fields and return the saved record. Throws
 * openenv_server_error's KilnError.
 */
export async function update_openenv_server(
  project_id: string,
  openenv_server_id: string,
  fields: OpenEnvServerFields,
): Promise<OpenEnvServer> {
  const { data, error, response } = await client.PATCH(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
    { params: { path: { project_id, openenv_server_id } }, body: fields },
  )
  if (error) {
    throw save_error(error, response)
  }
  return data
}

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

/** The ids of the project's archived OpenEnv servers. */
export async function load_archived_openenv_server_ids(
  project_id: string,
): Promise<Set<string>> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/openenv_servers",
    { params: { path: { project_id } } },
  )
  if (error) {
    throw error
  }
  return new Set(
    data
      .filter((openenv_server) => openenv_server.is_archived)
      .flatMap((openenv_server) =>
        openenv_server.id ? [openenv_server.id] : [],
      ),
  )
}

/** The JSON schema the OpenEnv server publishes for its reset arguments, or null. */
export async function load_openenv_server_reset_schema(
  project_id: string,
  openenv_server_id: string,
): Promise<Record<string, unknown> | null> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/reset_schema",
    { params: { path: { project_id, openenv_server_id } } },
  )
  if (error) {
    throw error
  }
  return data.reset_schema ?? null
}

/** The one OpenEnv a run with these tools would use, or why it can't run. */
export async function lookup_run_openenv_server(
  project_id: string,
  task_id: string,
  tool_ids: string[],
): Promise<RunOpenEnvServer> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/run_openenv_server",
    {
      params: { path: { project_id, task_id } },
      body: { tool_ids },
    },
  )
  if (error) {
    throw error
  }
  return data
}
