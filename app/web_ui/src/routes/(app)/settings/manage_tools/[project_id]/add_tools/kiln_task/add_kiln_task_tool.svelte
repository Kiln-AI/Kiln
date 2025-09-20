<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import type { Task, TaskRunConfig } from "$lib/types"
  import { current_project } from "$lib/stores"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import Warning from "$lib/ui/warning.svelte"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { uncache_available_tools } from "$lib/stores"

  let error: KilnError | null = null
  let submitting = false
  let name = ""
  let description = ""
  let selected_task: Task | null = null
  let tasks: Task[] = []
  let tasks_loading = false
  let tasks_loading_error: string | null = null

  onMount(async () => {
    await load_tasks($current_project?.id || "")
    for (const task of tasks) {
      // TODO: Can replace this with a request with a run config id (default)
      await load_task_run_configs($current_project?.id ?? "", task.id ?? "")
    }
  })

  function to_snake_case(str: string): string {
    return str
      .replace(/([A-Z])/g, "_$1")
      .toLowerCase()
      .replace(/^_/, "")
      .replace(/\s+/g, "_")
      .replace(/[^a-z0-9_]/g, "")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "")
  }

  $: if (selected_task) {
    name = to_snake_case(selected_task.name)
  }

  $: task_options = format_task_options(
    tasks,
    $run_configs_by_task_composite_id,
  )
  function format_task_options(
    tasks: Task[],
    run_configs: Record<string, TaskRunConfig[]>,
  ): OptionGroup[] {
    if (tasks.length === 0) {
      return []
    }
    let option_groups: OptionGroup[] = []
    option_groups.push({
      options: tasks.map((task) => ({
        label: task.name,
        value: task,
        description: default_run_config_description(task, run_configs),
      })),
    })
    return option_groups
  }

  function default_run_config_description(
    task: Task,
    run_configs: Record<string, TaskRunConfig[]>,
  ) {
    if (task.default_run_config_id) {
      let default_task_run_config = run_configs[task.id ?? ""]?.find(
        (config) => config.id === task.default_run_config_id,
      )
      if (default_task_run_config != null) {
        let properties = default_task_run_config.run_config_properties
        // TODO: Make this more readable
        return (
          (default_task_run_config.name ?? "") +
          ` | ${properties.model_name} (${properties.model_provider_name})` +
          ` | ${properties.prompt_id}` +
          ` | ${properties.tools_config?.tools.join(", ")}`
        )
      } else {
        return ""
      }
    } else {
      return ""
    }
  }

  $: load_tasks($current_project?.id || "")

  // TODO: Move this to a shared component since select_tasks_menu.svelte uses it too
  async function load_tasks(project_id: string) {
    if (!project_id) {
      tasks_loading = false
      tasks_loading_error = "No project selected"
      tasks = []
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
            project_id: project_id,
          },
        },
      })
      if (fetch_error) {
        throw fetch_error
      }
      tasks = tasks_data.filter((task) => task.default_run_config_id !== null)
    } catch (error) {
      tasks_loading_error = "Tasks failed to load: " + error
      tasks = []
    } finally {
      tasks_loading = false
    }
  }

  async function add_kiln_task_tool() {
    try {
      await client.POST("/api/projects/{project_id}/add_kiln_task_tool", {
        params: {
          path: {
            project_id: $page.params.project_id,
          },
        },
        body: {
          name: name,
          description: description,
          task_id: selected_task?.id || "",
          run_config_id: selected_task?.default_run_config_id || "",
          is_archived: false,
        },
      })

      // Delete the project_id from the available_tools, so next load it loads the updated list.
      uncache_available_tools($page.params.project_id)
      // Navigate to the tools page for the created tool
      goto(`/settings/manage_tools/${$page.params.project_id}`)
    } catch (e) {
      // TODO: Handle error
      error = createKilnError(e)
    }
  }

  let validate_name: (value: unknown) => string | null = (value: unknown) => {
    if (typeof value !== "string") {
      return "Tool name must be a string."
    }
    if (value.trim() === "") {
      return "Tool name must not be empty."
    }
    // Check for uppercase letters first
    if (/[A-Z]/.test(value)) {
      return "Tool name letters must be lowercase."
    }
    // Check for spaces
    if (value.includes(" ")) {
      return "Tool name cannot contain spaces. Use underscores instead (e.g. 'my_task_name')."
    }
    // Check if it starts or ends with underscore
    if (value.startsWith("_") || value.endsWith("_")) {
      return "Tool name cannot start or end with an underscore."
    }
    // Check if it contains consecutive underscores
    if (value.includes("__")) {
      return "Tool name cannot contain consecutive underscores."
    }
    // Check for any other invalid characters (special chars, etc.)
    if (!/^[a-z0-9_]+$/.test(value)) {
      return "Tool name cannot contain other characters besides lowercase letters, numbers, and underscores."
    }
    return null
  }

  let validate_description: (value: unknown) => string | null = (
    value: unknown,
  ) => {
    if (typeof value !== "string") {
      return "Tool description must be a string."
    }
    if (value.trim() === "") {
      return "Tool description must not be empty."
    }
    return null
  }
</script>

<div>
  <div class="max-w-4xl">
    {#if task_options.length > 0 && !tasks_loading_error}
      <FormContainer
        submit_label="Add"
        on:submit={add_kiln_task_tool}
        bind:error
        bind:submitting
      >
        <FormElement
          label="Kiln Task"
          bind:value={selected_task}
          id="task"
          inputType="fancy_select"
          fancy_select_options={task_options}
          placeholder={tasks_loading
            ? "Loading tasks..."
            : tasks_loading_error
              ? "Error loading tasks"
              : "Select a task"}
          disabled={tasks_loading}
          description="The task to add as a tool. The task's current default run options will be frozen in time and won't update if you change the task's default run config later."
          info_description="Only tasks with default run options set will available to add as tools."
        />

        {#if selected_task}
          <FormElement
            label="Name"
            id="task_name"
            description="The name for this tool. Used to identify the tool by the model. Must be unique within the project and be valid snake case (e.g. 'my_task_name')."
            bind:value={name}
            max_length={120}
            validator={validate_name}
          />

          <FormElement
            label="Description"
            inputType="textarea"
            id="task_description"
            description="A description of this tool. Used to describe the tool to the model."
            bind:value={description}
            validator={validate_description}
          />
        {/if}
      </FormContainer>
    {:else if tasks_loading_error}
      <div class="text-sm text-error">
        {tasks_loading_error}
      </div>
    {:else}
      <div class="flex flex-row gap-2">
        <Warning
          large_icon={true}
          warning_color="warning"
          warning_message="No tasks with default run options set available to add as tools."
        />
      </div>
    {/if}
  </div>
</div>
