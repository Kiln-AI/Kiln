import type { Task } from "$lib/types"
import { create_task_store, type TaskStoreConfig } from "./task_store_factory"

// Create singleton store instance that's shared across all pages
const tasks_store_config: TaskStoreConfig<Task> = {
  api_endpoint: "/api/projects/{project_id}/tasks/{task_id}",
  default_value: {} as Task, // Empty task object as default
  store_name: "tasks",
}

const tasks_store = create_task_store(tasks_store_config)

export const load_task = tasks_store.load
export const get_task = tasks_store.get
export const get_task_store = tasks_store.get_task_store
