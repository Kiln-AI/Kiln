import { client } from "$lib/api_client"
import type { OpenEnvServer, RunOpenEnvServer } from "$lib/types"

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
