import { writable, get } from "svelte/store"
import { client } from "$lib/api_client"

export type TaskCompositeId = string & { __brand: "TaskCompositeId" }

// Helper function to create composite keys for a task
export function get_task_composite_id(
  project_id: string,
  task_id: string,
): TaskCompositeId {
  return `${project_id}:${task_id}` as TaskCompositeId
}

export interface TaskStoreConfig<T> {
  api_endpoint: string
  default_value: T
  store_name: string
}

export interface TaskStore<T> {
  data: ReturnType<typeof writable<Record<TaskCompositeId, T>>>
  loading: ReturnType<typeof writable<Record<TaskCompositeId, boolean>>>
  load: (
    project_id: string,
    task_id: string,
    force_refresh?: boolean,
  ) => Promise<void>
  get: (
    project_id: string,
    task_id: string,
    force_refresh?: boolean,
  ) => Promise<T | null>
  get_task_store: (
    project_id: string,
    task_id: string,
  ) => ReturnType<typeof writable<T | null>>
}

export function create_task_store<T>(config: TaskStoreConfig<T>): TaskStore<T> {
  const data = writable<Record<TaskCompositeId, T>>({})
  const loading = writable<Record<TaskCompositeId, boolean>>({})
  const loadingPromises: Record<TaskCompositeId, Promise<void>> = {}
  const individualStores: Record<
    TaskCompositeId,
    ReturnType<typeof writable<T | null>>
  > = {}

  async function load(
    project_id: string,
    task_id: string,
    force_refresh: boolean = false,
  ): Promise<void> {
    const composite_key = get_task_composite_id(project_id, task_id)

    if (composite_key in loadingPromises) {
      if (force_refresh) {
        // If forcing refresh and there's an existing request, wait for it to complete first (still retry even on failure)
        try {
          await loadingPromises[composite_key]
        } catch (error) {
          console.warn(
            `Previous ${config.store_name} load failed; retrying due to force refresh: `,
            error,
          )
        }
      } else {
        // Return existing promise if already loading this specific task
        return loadingPromises[composite_key]
      }
    }

    // Create and store the promise
    const promise = (async () => {
      // Set loading state to true
      loading.update((loadingState) => ({
        ...loadingState,
        [composite_key]: true,
      }))

      try {
        const { data: responseData, error } = await client.GET(
          config.api_endpoint as Parameters<typeof client.GET>[0],
          {
            params: {
              path: {
                project_id: project_id,
                task_id: task_id,
              },
            },
          } as Parameters<typeof client.GET>[1],
        )
        if (error) {
          throw error
        }

        // Update the store with the new data for this specific task using composite key
        const taskData = responseData || config.default_value
        data.update((currentData) => ({
          ...currentData,
          [composite_key]: taskData,
        }))
      } catch (error) {
        console.error(`Failed to load ${config.store_name}: `, error)
        throw error
      } finally {
        // Set loading state to false
        loading.update((loadingState) => ({
          ...loadingState,
          [composite_key]: false,
        }))

        // Clean up the promise from the map
        delete loadingPromises[composite_key]
      }
    })()

    loadingPromises[composite_key] = promise
    return promise
  }

  async function get_data(
    project_id: string,
    task_id: string,
    force_refresh: boolean = false,
  ): Promise<T | null> {
    await load(project_id, task_id, force_refresh)
    const composite_key = get_task_composite_id(project_id, task_id)
    const current_data = get(data)
    return current_data[composite_key] || null
  }

  function get_task_store(
    project_id: string,
    task_id: string,
  ): ReturnType<typeof writable<T | null>> {
    const composite_key = get_task_composite_id(project_id, task_id)

    // Return existing store if it exists
    if (individualStores[composite_key]) {
      return individualStores[composite_key]
    }

    // Create new individual store
    const individualStore = writable<T | null>(null)
    individualStores[composite_key] = individualStore

    // Subscribe to the main data store to keep individual store in sync
    const _ = data.subscribe((allData) => {
      const taskData = allData[composite_key] || null
      individualStore.set(taskData)
    })

    // Store the unsubscribe function for potential cleanup (though we don't expose it)
    // The individual store will stay in sync as long as it exists

    return individualStore
  }

  return {
    data,
    loading,
    load,
    get: get_data,
    get_task_store,
  }
}
