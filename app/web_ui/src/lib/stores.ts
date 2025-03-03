import { writable, get } from "svelte/store"
import { dev } from "$app/environment"
import type {
  Project,
  Task,
  AvailableModels,
  ProviderModels,
  PromptResponse,
} from "./types"
import { client } from "./api_client"
import { createKilnError } from "$lib/utils/error_handlers"

export type AllProjects = {
  projects: Project[]
  error: string | null
}

// UI State stored in the browser. For more client centric state
export type UIState = {
  current_project_id: string | null
  current_task_id: string | null
  selected_model: string | null
}

export const default_ui_state: UIState = {
  current_project_id: null,
  current_task_id: null,
  selected_model: null,
}

// Private, used to store the current project, and task ID
export const ui_state = localStorageStore("ui_state", default_ui_state)

// These stores store nice structured data. They are auto-updating based on the ui_state and server calls to load data
export const projects = writable<AllProjects | null>(null)
export const current_project = writable<Project | null>(null)
export const current_task = writable<Task | null>(null)
export const current_task_prompts = writable<PromptResponse | null>(null)

let previous_ui_state: UIState = default_ui_state

// Live update the structured data stores based on the ui_state
ui_state.subscribe((state) => {
  if (state.current_project_id != previous_ui_state.current_project_id) {
    current_project.set(get_current_project())
  }
  if (state.current_task_id != previous_ui_state.current_task_id) {
    load_current_task(get(current_project))
  }
  previous_ui_state = { ...state }
})

projects.subscribe((all_projects) => {
  if (all_projects) {
    current_project.set(get_current_project())
    load_current_task(get(current_project))
  }
})

function get_current_project(): Project | null {
  const all_projects = get(projects)

  if (!all_projects) {
    return null
  }
  const current_project_id = get(ui_state).current_project_id
  if (!current_project_id) {
    return null
  }
  const project = all_projects.projects.find(
    (project) => project.id === current_project_id,
  )
  if (!project) {
    return null
  }
  return project
}

export async function load_projects() {
  try {
    const {
      data: project_list, // only present if 2XX response
      error, // only present if 4XX or 5XX response
    } = await client.GET("/api/projects")
    if (error) {
      throw error
    }

    const all_projects: AllProjects = {
      projects: project_list,
      error: null,
    }
    projects.set(all_projects)
  } catch (error: unknown) {
    const all_projects: AllProjects = {
      projects: [],
      error: "Issue loading projects. " + createKilnError(error).getMessage(),
    }
    projects.set(all_projects)
  }
}

// Custom function to create a localStorage-backed store
function localStorageStore<T>(key: string, initialValue: T) {
  // Check if localStorage is available
  const isBrowser = typeof window !== "undefined" && window.localStorage

  // Get stored value from localStorage or use initial value
  const storedValue = isBrowser
    ? JSON.parse(localStorage.getItem(key) || "null")
    : null
  const store = writable(storedValue !== null ? storedValue : initialValue)

  if (isBrowser) {
    // Subscribe to changes and update localStorage
    store.subscribe((value) => localStorage.setItem(key, JSON.stringify(value)))
  }

  return store
}

export async function load_task(
  project_id: string,
  task_id: string,
): Promise<Task | null> {
  const {
    data, // only present if 2XX response
    error, // only present if 4XX or 5XX response
  } = await client.GET("/api/projects/{project_id}/tasks/{task_id}", {
    params: {
      path: {
        project_id: project_id,
        task_id: task_id,
      },
    },
  })
  if (error) {
    throw error
  }
  return data
}

export async function load_current_task(project: Project | null) {
  let task: Task | null = null
  try {
    const task_id = get(ui_state).current_task_id
    if (!project || !project?.id || !task_id) {
      return
    }
    task = await load_task(project.id, task_id)

    // Load the current task's prompts after 50ms, as it's not the most critical data
    setTimeout(() => {
      load_available_prompts()
    }, 50)
  } catch (error: unknown) {
    // Can't load this task, likely deleted. Clear the ID, which will force the user to select a new task
    if (dev) {
      alert(
        "Removing current_task_id from UI state: " +
          createKilnError(error).getMessage(),
      )
    }
    task = null
    ui_state.set({
      ...get(ui_state),
      current_task_id: null,
    })
  } finally {
    current_task.set(task)
  }
}

// Available models for each provider
export const available_models = writable<AvailableModels[]>([])

export async function load_available_models() {
  try {
    const { data, error } = await client.GET("/api/available_models")
    if (error) {
      throw error
    }
    available_models.set(data)
  } catch (error: unknown) {
    console.error(createKilnError(error).getMessage())
    available_models.set([])
  }
}

// Model Info
export const model_info = writable<ProviderModels | null>(null)

export async function load_model_info() {
  try {
    if (get(model_info)) {
      return
    }
    const { data, error } = await client.GET("/api/providers/models")
    if (error) {
      throw error
    }
    model_info.set(data)
  } catch (error: unknown) {
    console.error(createKilnError(error).getMessage())
    model_info.set(null)
  }
}

export function model_name(
  model_id: string | number | undefined,
  provider_models: ProviderModels | null,
): string {
  if (!model_id) {
    return "Unknown"
  }
  // Could be a number, so convert to string
  model_id = "" + model_id
  const model = provider_models?.models[model_id]
  return model?.name || model_id
}

export function provider_name_from_id(provider_id: string): string {
  if (!provider_id) {
    return "Unknown"
  }
  const provider = get(available_models).find(
    (provider) => provider.provider_id === provider_id,
  )
  return provider?.provider_name || provider_id
}

export function prompt_name_from_id(prompt_id: string): string {
  // Attempt to lookup a nice name for the prompt. First from named prompts, then from generators
  // Special case for fine-tuned prompts
  let prompt_name: string | undefined = undefined
  if (prompt_id && prompt_id.startsWith("fine_tune_prompt::")) {
    prompt_name = "Fine-Tune Prompt"
  }
  if (!prompt_name) {
    prompt_name = get(current_task_prompts)?.prompts.find(
      (prompt) => prompt.id === prompt_id,
    )?.name
  }
  if (!prompt_name) {
    prompt_name = get(current_task_prompts)?.generators.find(
      (generator) => generator.id === prompt_id,
    )?.name
  }
  if (!prompt_name) {
    prompt_name = prompt_id
  }
  return prompt_name
}

// Available prompts for the current
export async function load_available_prompts() {
  const project = get(current_project)
  const task = get(current_task)
  if (!project || !task || !project.id || !task.id) {
    current_task_prompts.set(null)
    return
  }
  try {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/task/{task_id}/prompts",
      {
        params: {
          path: {
            project_id: project.id,
            task_id: task.id,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    current_task_prompts.set(data)
  } catch (error: unknown) {
    console.error(createKilnError(error).getMessage())
    current_task_prompts.set(null)
  }
}
