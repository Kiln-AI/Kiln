<script lang="ts">
  import { current_project, projects, current_task } from "$lib/stores"
  import type { Project, Task } from "$lib/types"
  import { ui_state } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import { createEventDispatcher } from "svelte"

  const dispatch = createEventDispatcher()

  export let new_project_url = "/settings/create_project"
  export let new_task_url = "/settings/create_task"

  $: project_list = $projects?.projects || []
  let manually_selected_project: Project | null | undefined = undefined
  let tasks_loading = false
  let tasks_loading_error: string | null = null
  let selected_project_tasks: Task[] = []
  let last_loaded_project_id: string | null = null
  let show_project_pane = false
  let load_request_counter = 0
  let previous_task_id: string | null | undefined = undefined

  $: selected_project =
    manually_selected_project === null
      ? null
      : manually_selected_project || $current_project

  function select_project(project: Project) {
    if (project?.id === selected_project?.id) {
      show_project_pane = false
      return
    }
    manually_selected_project = project
    show_project_pane = false
  }

  $: {
    const force = $current_task?.id !== previous_task_id
    if (force) {
      previous_task_id = $current_task?.id
    }
    load_tasks(selected_project, { force })
  }

  async function load_tasks(
    project: Project | null,
    { force = false }: { force?: boolean } = {},
  ) {
    if (project == null || !project.id) {
      tasks_loading = false
      tasks_loading_error = "No project selected"
      last_loaded_project_id = null
      return
    }
    if (!force && project.id === last_loaded_project_id) {
      return
    }
    const request_id = ++load_request_counter
    try {
      tasks_loading = true
      tasks_loading_error = null
      const { data: tasks_data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks",
        {
          params: {
            path: {
              project_id: project.id,
            },
          },
        },
      )
      if (request_id !== load_request_counter) {
        return
      }
      if (fetch_error) {
        throw fetch_error
      }
      selected_project_tasks = tasks_data
      last_loaded_project_id = project.id
    } catch (error) {
      if (request_id !== load_request_counter) {
        return
      }
      tasks_loading_error = "Tasks failed to load: " + error
      selected_project_tasks = []
      last_loaded_project_id = null
    } finally {
      if (request_id === load_request_counter) {
        tasks_loading = false
      }
    }
  }

  function select_task(task: Task) {
    if (selected_project == null) {
      return
    }
    ui_state.update((state) => {
      return {
        ...state,
        current_task_id: task.id,
        current_project_id: selected_project.id,
      }
    })

    goto(`/`, { replaceState: true })
    dispatch("dismiss")
  }
</script>

<div class="flex flex-col gap-3">
  <button
    class="md:hidden flex items-center gap-2 px-3 py-2 rounded-xl border border-base-300 bg-base-100 text-sm font-medium w-full text-left"
    on:click={() => (show_project_pane = !show_project_pane)}
  >
    <img src="/images/sm_folder.svg" alt="Project" class="w-4 h-4 opacity-60" />
    <span class="grow truncate">
      {selected_project?.name || "Select a project"}
    </span>
    <svg
      class="w-3 h-3 shrink-0 transition-transform {show_project_pane
        ? 'rotate-180'
        : ''}"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  </button>

  <div class="grid md:grid-cols-[320px_1fr] gap-4">
    <section
      class="border border-base-300 rounded-2xl overflow-hidden flex flex-col {show_project_pane
        ? ''
        : 'hidden md:flex'}"
    >
      <div class="bg-base-200 px-3.5 py-2.5 flex items-center gap-2">
        <div class="grow">
          <div class="text-sm font-semibold">Projects</div>
          <div class="text-xs text-base-content/60">
            {project_list.length}
            {project_list.length === 1 ? "project" : "projects"}
          </div>
        </div>
        <a
          href={new_project_url}
          class="btn btn-sm btn-ghost"
          on:click={() => dispatch("dismiss")}>+ New Project</a
        >
      </div>
      <div
        class="overflow-y-auto px-1.5 py-1.5 flex flex-col gap-0.5 min-h-[200px] max-h-[400px]"
      >
        {#each project_list as project}
          <button
            class="flex items-start gap-2.5 px-3.5 py-3 rounded-xl w-full text-left transition-colors
              {project.id === selected_project?.id
              ? 'bg-primary/10 border border-primary/20'
              : 'hover:bg-base-200 border border-transparent'}"
            on:click={() => select_project(project)}
          >
            <img
              src="/images/sm_folder.svg"
              alt="Project"
              class="w-4 h-4 opacity-60 mt-0.5 shrink-0"
            />
            <div class="min-w-0">
              <div class="text-sm font-medium truncate">{project.name}</div>
              {#if project.description}
                <div class="text-xs text-base-content/60 truncate">
                  {project.description}
                </div>
              {/if}
            </div>
          </button>
        {/each}
      </div>
    </section>

    <section
      class="border border-base-300 rounded-2xl overflow-hidden flex flex-col {show_project_pane
        ? 'hidden md:flex'
        : ''}"
    >
      {#if !selected_project}
        <div
          class="flex flex-col items-center justify-center min-h-[300px] text-base-content/40 gap-3"
        >
          <svg
            class="w-10 h-10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <span class="text-sm">Select a project to view its tasks</span>
        </div>
      {:else}
        <div class="bg-base-200 px-3.5 py-2.5 flex items-center gap-2">
          <div class="grow">
            <div class="text-sm font-semibold">Tasks</div>
            <div class="text-xs text-base-content/60">
              {#if tasks_loading}
                Loading...
              {:else if tasks_loading_error}
                Error loading tasks
              {:else}
                {selected_project_tasks.length}
                {selected_project_tasks.length === 1 ? "task" : "tasks"} in {selected_project.name}
              {/if}
            </div>
          </div>
          <a
            href={new_task_url + "/" + (selected_project?.id || "")}
            class="btn btn-sm btn-ghost"
            on:click={() => dispatch("dismiss")}>+ New Task</a
          >
        </div>
        <div
          class="overflow-y-auto px-1.5 py-1.5 flex flex-col gap-0.5 min-h-[200px] max-h-[400px]"
        >
          {#if tasks_loading}
            <div class="flex items-center justify-center h-32">
              <span class="loading loading-spinner loading-md"></span>
            </div>
          {:else if tasks_loading_error}
            <div class="flex items-center justify-center h-32">
              <div class="text-center">
                <div class="font-bold text-sm">Error</div>
                <div class="text-sm text-base-content/60">
                  {tasks_loading_error}
                </div>
              </div>
            </div>
          {:else}
            {#each selected_project_tasks as task}
              <button
                class="flex items-center gap-2.5 px-3.5 py-3 rounded-xl w-full text-left transition-colors
                  {task.id === $current_task?.id &&
                selected_project?.id === $current_project?.id
                  ? 'bg-primary/10 border border-primary/20'
                  : 'hover:bg-base-200 border border-transparent'}"
                on:click={() => select_task(task)}
              >
                <svg
                  class="w-4 h-4 opacity-60 shrink-0"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                >
                  <path
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                <div class="min-w-0 grow">
                  <div class="text-sm font-medium truncate">{task.name}</div>
                </div>
              </button>
            {/each}
          {/if}
        </div>
      {/if}
    </section>
  </div>
</div>
