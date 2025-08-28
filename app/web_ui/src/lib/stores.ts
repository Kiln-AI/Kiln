import { writable, get } from "svelte/store"
import { dev } from "$app/environment"
import type {
  Project,
  Task,
  AvailableModels,
  ProviderModels,
  PromptResponse,
  RatingOptionResponse,
  TaskRequirement,
  ModelDetails,
  EmbeddingProvider,
  EmbeddingModelDetails,
  ToolSetApiDescription,
} from "./types"
import { client } from "./api_client"
import { createKilnError } from "$lib/utils/error_handlers"
import type { Writable } from "svelte/store"
import type { ProviderModel } from "./types"

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

// UI Stores we want persisted across page loads
export const fine_tune_target_model: Writable<string | null> =
  localStorageStore("fine_tune_target_model", null)

// Rating options for the current task
export const current_task_rating_options =
  writable<RatingOptionResponse | null>(null)

let previous_ui_state: UIState = default_ui_state

// Live update the structured data stores based on the ui_state
ui_state.subscribe((state) => {
  if (state.current_project_id != previous_ui_state.current_project_id) {
    current_project.set(get_current_project())
  }
  if (state.current_task_id != previous_ui_state.current_task_id) {
    // invalidate task caches. Rating options will load on demand.
    current_task.set(null)
    current_task_rating_options.set(null)
    current_task_prompts.set(null)
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
export function localStorageStore<T>(key: string, initialValue: T) {
  // Check if localStorage is available
  const isBrowser = typeof window !== "undefined" && window.localStorage

  // Get stored value from localStorage or use initial value
  const storedValue = isBrowser
    ? JSON.parse(localStorage.getItem(key) || "null")
    : null
  const store = writable(storedValue !== null ? storedValue : initialValue)

  if (isBrowser) {
    // Subscribe to changes and update localStorage
    store.subscribe((value) => {
      const stringified = JSON.stringify(value)
      // 1MB is a reasonable limit. Most browsers have a 5MB limit total for localStorage.
      if (stringified.length > 1 * 1024 * 1024) {
        console.error(
          "Skipping localStorage save for " + key + " as it's too large (>1MB)",
        )
      } else {
        localStorage.setItem(key, stringified)
      }
    })
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

// Available tools, by project ID
export const available_tools = writable<
  Record<string, ToolSetApiDescription[]>
>({})
let loading_project_tools: string[] = []

export async function load_available_tools(
  project_id: string,
  force: boolean = false,
) {
  // Only allow one request per project at a time
  if (loading_project_tools.includes(project_id)) {
    return
  }

  // Don't load if already loaded, unless forced
  if (get(available_tools)[project_id] && !force) {
    return
  }

  try {
    loading_project_tools.push(project_id)

    const { data, error } = await client.GET(
      "/api/projects/{project_id}/available_tools",
      {
        params: {
          path: {
            project_id: project_id,
          },
        },
      },
    )
    if (error) {
      throw error
    }
    available_tools.set({
      ...get(available_tools),
      [project_id]: data,
    })
  } catch (error: unknown) {
    console.error(
      "Failed to load tools for project " +
        project_id +
        ": " +
        createKilnError(error).getMessage(),
    )
  } finally {
    loading_project_tools = loading_project_tools.filter(
      (id) => id !== project_id,
    )
  }
}

// Available models for each provider
export const available_models = writable<AvailableModels[]>([])
let available_models_loaded: "not_loaded" | "loading" | "loaded" = "not_loaded"

export async function load_available_models() {
  try {
    if (
      available_models_loaded === "loading" ||
      available_models_loaded === "loaded"
    ) {
      // Block parallel requests or if already loaded
      return
    }
    available_models_loaded = "loading"
    const { data, error } = await client.GET("/api/available_models")
    if (error) {
      throw error
    }
    available_models.set(data)
    available_models_loaded = "loaded"
  } catch (error: unknown) {
    console.error(createKilnError(error).getMessage())
    available_models.set([])
    available_models_loaded = "not_loaded"
  }
}

// Available embedding models for each provider
export const available_embedding_models = writable<EmbeddingProvider[]>([])
let available_embedding_models_loaded: "not_loaded" | "loading" | "loaded" =
  "not_loaded"

export async function load_available_embedding_models() {
  try {
    if (
      available_embedding_models_loaded === "loading" ||
      available_embedding_models_loaded === "loaded"
    ) {
      return
    }
    available_embedding_models_loaded = "loading"
    const { data, error } = await client.GET("/api/available_embedding_models")
    if (error) {
      throw error
    }
    available_embedding_models.set(data)
    available_embedding_models_loaded = "loaded"
  } catch (error: unknown) {
    console.error(createKilnError(error).getMessage())
    available_embedding_models.set([])
    available_embedding_models_loaded = "not_loaded"
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

export function available_model_details(
  model_id: string | null,
  provider_id: string | null,
  available_models: AvailableModels[],
): ModelDetails | null {
  // No-op if already loaded
  load_available_models()

  if (!model_id || !provider_id) {
    return null
  }

  // Find the model in the available models list which has fine-tunes and custom models
  for (const provider of available_models) {
    if (provider.provider_id !== provider_id) {
      continue
    }
    const models = provider.models || []
    for (const model of models) {
      if (model.id === model_id) {
        return model
      }
    }
  }
  return null
}

export function get_model_info(
  model_id: string | number | undefined,
  provider_models: ProviderModels | null,
): ProviderModel | null {
  if (!model_id) {
    return null
  }
  // Could be a number, so convert to string
  model_id = "" + model_id
  const model = provider_models?.models[model_id]
  if (model) {
    return model
  }

  // Or find the model in the available models list which has fine-tunes and custom models
  for (const provider of get(available_models)) {
    // No filter on provider_id, as we want to find the model in any provider
    const models = provider.models || []
    for (const model of models) {
      if (model.id === model_id) {
        return model
      }
    }
  }
  return null
}

export function get_embedding_model_info(
  model_id: string | number | undefined,
  provider_id: string | null,
): EmbeddingModelDetails | null {
  if (!model_id) {
    return null
  }

  for (const provider of get(available_embedding_models)) {
    if (provider.provider_id === provider_id) {
      const models = provider.models || []
      for (const model of models) {
        if (model.id === model_id) {
          return model
        }
      }
    }
  }
  return null
}

export function model_name(
  model_id: string | number | undefined,
  provider_models: ProviderModels | null,
): string {
  if (!model_id) {
    return "Unknown"
  }

  const model = get_model_info(model_id, provider_models)
  if (model?.name) {
    return model.name
  }
  return "Model ID: " + model_id
}

export function embedding_model_name(
  model_id: string | number | undefined,
  provider_id: string | null,
): string {
  if (!model_id) {
    return "Unknown"
  }
  const model = get_embedding_model_info(model_id, provider_id)
  if (model?.name) {
    return model.name
  }
  return "Model ID: " + model_id
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

export function prompt_name_from_id(
  prompt_id: string,
  prompt_response: PromptResponse | null,
): string {
  // Dispatch a request to load the prompts if we don't have them yet
  if (!prompt_response) {
    load_available_prompts()
  }
  // Attempt to lookup a nice name for the prompt. First from named prompts, then from generators
  // Special case for fine-tuned prompts
  let prompt_name: string | undefined = undefined
  if (prompt_id && prompt_id.startsWith("fine_tune_prompt::")) {
    prompt_name = "Fine-Tune Prompt"
  }
  if (!prompt_name) {
    prompt_name = prompt_response?.prompts.find(
      (prompt) => prompt.id === prompt_id,
    )?.name
  }
  if (!prompt_name) {
    prompt_name = prompt_response?.generators.find(
      (generator) => generator.id === prompt_id,
    )?.name
  }
  if (!prompt_name) {
    prompt_name = prompt_id
  }
  return prompt_name
}

// Available prompts for the current task. Lock to avoid parallel requests.
let is_loading_prompts = false
export async function load_available_prompts() {
  const project = get(current_project)
  const task = get(current_task)
  if (!project || !task || !project.id || !task.id) {
    current_task_prompts.set(null)
    return
  }

  try {
    // Return early if already loading
    if (is_loading_prompts) {
      return
    }
    is_loading_prompts = true
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
  } finally {
    is_loading_prompts = false
  }
}

// Lock to avoid parallel requests for rating options
let is_loading_rating_options = false

export async function load_rating_options() {
  const project = get(current_project)
  const task = get(current_task)
  if (!project || !task || !project.id || !task.id) {
    current_task_rating_options.set(null)
    return
  }

  try {
    // Return early if already loading
    if (is_loading_rating_options) {
      return
    }
    is_loading_rating_options = true
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/rating_options",
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
    current_task_rating_options.set(data)
  } catch (error: unknown) {
    console.error(createKilnError(error).getMessage())
    current_task_rating_options.set(null)
  } finally {
    is_loading_rating_options = false
  }
}

export function rating_options_for_sample(
  rating_options: RatingOptionResponse | null,
  tags: string[],
): TaskRequirement[] {
  // Dispatch a request to load the rating options if we don't have them yet
  if (!rating_options) {
    load_rating_options()
    return []
  }

  // Filter rating options based on tags and return just the requirements
  return rating_options.options
    .filter((option) => {
      // Show if it's marked for all items
      if (option.show_for_all) {
        return true
      }
      // Show if any of the item's tags match the option's tags
      return option.show_for_tags.some((tag: string) => tags.includes(tag))
    })
    .map((option) => option.requirement)
}

export function get_model_friendly_name(model_id: string): string {
  const model = get_model_info(model_id, get(model_info))
  if (model?.name) {
    return model.name
  }
  return model_id
}
