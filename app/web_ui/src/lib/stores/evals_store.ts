import { client } from "$lib/api_client"
import type { Eval } from "$lib/types"
import posthog from "posthog-js"

export async function set_current_eval_config(
  project_id: string,
  task_id: string,
  eval_id: string,
  eval_config_id: string | null,
): Promise<Eval> {
  const config_id = eval_config_id === null ? "None" : eval_config_id

  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/set_current_eval_config/{eval_config_id}",
    {
      params: {
        path: {
          project_id,
          task_id,
          eval_id,
          eval_config_id: config_id,
        },
      },
    },
  )

  if (error) {
    throw error
  }

  posthog.capture("set_current_eval_config", {})

  return data
}
