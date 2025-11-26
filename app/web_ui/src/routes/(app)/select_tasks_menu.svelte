<script lang="ts">
  import { current_project, projects, current_task } from "$lib/stores"
  import type { Project, Task } from "$lib/types"
  import { ui_state } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"

  let id = "select-tasks-menu-" + Math.random().toString(36)

  export let new_project_url = "/settings/create_project"
  export let new_task_url = "/settings/create_task"

  $: project_list = $projects?.projects || []
  // Undefined should fallback. Null is manually selected none
  let manually_selected_project: Project | null | undefined = undefined
  let tasks_loading = false
  let tasks_loading_error: string | null = null
  let selected_project_tasks: Task[] = []

  $: selected_project =
    manually_selected_project === null
      ? null
      : manually_selected_project || $current_project

  function select_project(project: Project) {
    if (project?.id == selected_project?.id) {
      // Actually deselect it
      manually_selected_project = null
      return
    }
    manually_selected_project = project
    load_tasks(project)
  }

  $: load_tasks(selected_project)

  // Reload when the current task changes. Sometimes the task is deleted or a new one is created.
  current_task.subscribe(() => {
    load_tasks(selected_project)
  })

  async function load_tasks(project: Project | null) {
    if (project == null || !project.id) {
      tasks_loading = false
      tasks_loading_error = "No project selected"
      return
    }
    try {
      tasks_loading = true
      tasks_loading_error = null
      const {
        data: tasks_data, // only present if 2XX response
        error: fetch_error, // only present if 4XX or 5XX response
      } = await client.GET("/api/projects/{project_id}/tasks", {
        params: {
          path: {
            project_id: project.id,
          },
        },
      })
      if (fetch_error) {
        throw fetch_error
      }
      selected_project_tasks = tasks_data
    } catch (error) {
      tasks_loading_error = "Tasks failed to load: " + error
      selected_project_tasks = []
    } finally {
      tasks_loading = false
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
    close_menu()
  }

  function close_menu() {
    // Close the menu
    const menu = document.getElementById(id)
    if (
      menu &&
      menu.parentElement &&
      menu.parentElement instanceof HTMLDetailsElement
    ) {
      menu.parentElement.open = false
    }
  }
</script>

<ul class="menu menu-md bg-base-200 rounded-box" {id}>
  {#each project_list as project}
    <li>
      <button
        on:click={() => select_project(project)}
        class="flex flex-row pr-1"
      >
        <div class="grow">
          <span class="badge badge-secondary badge-outline">Project</span>
          {project.name}
        </div>
        <div>
          {#if project.id == selected_project?.id}
            <svg
              fill="#000000"
              class="w-3 h-3"
              version="1.1"
              id="Layer_1"
              xmlns="http://www.w3.org/2000/svg"
              xmlns:xlink="http://www.w3.org/1999/xlink"
              viewBox="0 0 407.437 407.437"
              xml:space="preserve"
            >
              <polygon
                points="386.258,91.567 203.718,273.512 21.179,91.567 0,112.815 203.718,315.87 407.437,112.815 "
              />
            </svg>
          {:else}
            <svg
              fill="#000000"
              class="w-3 h-3"
              version="1.1"
              id="Layer_1"
              xmlns="http://www.w3.org/2000/svg"
              xmlns:xlink="http://www.w3.org/1999/xlink"
              viewBox="0 0 407.436 407.436"
              xml:space="preserve"
            >
              <polygon
                points="203.718,91.567 0,294.621 21.179,315.869 203.718,133.924 386.258,315.869 407.436,294.621 "
              />
            </svg>
          {/if}
        </div>
      </button>
      {#if project.id == selected_project?.id}
        <ul>
          {#if tasks_loading}
            <li
              class="flex justify-center place-items-center place-content-center h-32"
            >
              <span class="loading loading-spinner loading-md"></span>
            </li>
          {:else if tasks_loading_error}
            <li
              class="flex justify-center place-items-center place-content-center h-32"
            >
              <span class="flex flex-col">
                <span class="font-bold">Error</span>
                <span class="">{tasks_loading_error}</span>
              </span>
            </li>
          {:else}
            {#each selected_project_tasks as task}
              <li>
                <button on:click={() => select_task(task)}>
                  {task.name}
                </button>
              </li>
            {/each}
          {/if}
          <li class="">
            <a href={new_task_url + "/" + (project?.id || "")}>
              <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. https://www.svgrepo.com/svg/491465/plus-circle -->
              <svg
                class="w-4 h-4"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  fill-rule="evenodd"
                  clip-rule="evenodd"
                  d="M1 12C1 5.92487 5.92487 1 12 1C18.0751 1 23 5.92487 23 12C23 18.0751 18.0751 23 12 23C5.92487 23 1 18.0751 1 12ZM12.5 5.5C13.0523 5.5 13.5 5.94772 13.5 6.5V10.5H17.5C18.0523 10.5 18.5 10.9477 18.5 11.5V12.5C18.5 13.0523 18.0523 13.5 17.5 13.5H13.5V17.5C13.5 18.0523 13.0523 18.5 12.5 18.5H11.5C10.9477 18.5 10.5 18.0523 10.5 17.5V13.5H6.5C5.94772 13.5 5.5 13.0523 5.5 12.5V11.5C5.5 10.9477 5.94772 10.5 6.5 10.5H10.5V6.5C10.5 5.94772 10.9477 5.5 11.5 5.5H12.5Z"
                  fill="#000000"
                />
              </svg>
              New Task
            </a>
          </li>
        </ul>
      {/if}
    </li>
  {/each}
  <li class="pt-4">
    <a href={new_project_url}>
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. https://www.svgrepo.com/svg/491465/plus-circle -->
      <svg
        class="w-4 h-4"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          fill-rule="evenodd"
          clip-rule="evenodd"
          d="M1 12C1 5.92487 5.92487 1 12 1C18.0751 1 23 5.92487 23 12C23 18.0751 18.0751 23 12 23C5.92487 23 1 18.0751 1 12ZM12.5 5.5C13.0523 5.5 13.5 5.94772 13.5 6.5V10.5H17.5C18.0523 10.5 18.5 10.9477 18.5 11.5V12.5C18.5 13.0523 18.0523 13.5 17.5 13.5H13.5V17.5C13.5 18.0523 13.0523 18.5 12.5 18.5H11.5C10.9477 18.5 10.5 18.0523 10.5 17.5V13.5H6.5C5.94772 13.5 5.5 13.0523 5.5 12.5V11.5C5.5 10.9477 5.94772 10.5 6.5 10.5H10.5V6.5C10.5 5.94772 10.9477 5.5 11.5 5.5H12.5Z"
          fill="#000000"
        />
      </svg>
      New Project</a
    >
  </li>
</ul>
