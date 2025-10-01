import type { PromptResponse } from "$lib/types"
import { create_task_store, type TaskStoreConfig } from "./task_store_factory"

// Create singleton store instance that's shared across all pages
const prompts_store_config: TaskStoreConfig<PromptResponse> = {
  api_endpoint: "/api/projects/{project_id}/task/{task_id}/prompts",
  default_value: { generators: [], prompts: [] },
  store_name: "task_prompts",
}

const prompts_store = create_task_store(prompts_store_config)

export const load_task_prompts = prompts_store.load
export const get_task_prompts = prompts_store.get
export const get_task_prompts_store = prompts_store.get_task_store

// TODO: Replace all usage of load_available_prompts() with prompts_store.load(...) and remove this and do:
// export const load_task_prompts = prompts_store.load
// export async function load_task_prompts(
//   project_id: string,
//   task_id: string,
//   force_refresh: boolean = false,
// ): Promise<void> {
//   await load_available_prompts() // For the case task_id === current_task.id and other clients use load_available_prompts() still
//   return prompts_store.load(project_id, task_id, force_refresh)
// }
