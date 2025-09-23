<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import Dialog from "$lib/ui/dialog.svelte"
  import { client } from "$lib/api_client"
  import type { Task, TaskRunConfig } from "$lib/types"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
    get_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import {
    current_task_prompts,
    load_available_models,
    load_available_prompts,
    load_model_info,
    model_info,
    model_name,
    provider_name_from_id,
    uncache_available_tools,
  } from "$lib/stores"
  import { getRunConfigPromptDisplayName } from "$lib/utils/run_config_formatters"

  let error: KilnError | null = null
  let submitting = false
  let name: string | null = null
  let description = ""
  let selected_task_id: string | null = null
  let tasks: Task[] = []
  let tasks_loading_error: string | null = null
  let data_loaded = false
  let no_default_config_dialog: Dialog | null = null
  let task_name_for_dialog: string | null = null

  onMount(async () => {
    const project_id = $page.params.project_id ?? ""

    await load_tasks(project_id)
    for (const task of tasks) {
      // TODO: Can replace this with a request with a run config id (default)
      await load_task_run_configs(project_id, task.id ?? "")
    }

    await load_available_prompts()
    await load_available_models()
    await load_model_info()

    // Check for URL parameters to pre-fill form (for cloning)
    const urlParams = new URLSearchParams($page.url.search)
    const cloneName = urlParams.get("name")
    const cloneDescription = urlParams.get("description")
    const cloneTaskId = urlParams.get("task_id")

    if (cloneName) {
      name = cloneName
    }
    if (cloneDescription) {
      description = cloneDescription
    }
    if (cloneTaskId) {
      selected_task_id = cloneTaskId
    }

    data_loaded = true
  })

  function to_snake_case(str: string): string {
    return str
      .replace(/([A-Z])/g, "_$1")
      .toLowerCase()
      .replace(/^_/, "")
      .replace(/\s+/g, "_")
      .replace(/-/g, "_")
      .replace(/[^a-z0-9_]/g, "")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "")
  }

  $: if (selected_task_id) {
    show_dialog_if_needed()
  }

  $: if (selected_task_id && name === null) {
    // Only set name if it's null (initial selection)
    const task = tasks.find((t) => t.id === selected_task_id)
    if (task) {
      name = to_snake_case(task.name)
    }
  }

  // Handle cloning - if we have a pre-filled name from URL params, modify it
  $: if (name && $page.url.search.includes("name=")) {
    // This is a clone operation, modify the name to indicate it's a copy
    if (!name.startsWith("copy_of_")) {
      name = `copy_of_${name}`
    }
  }

  async function show_dialog_if_needed() {
    const task = tasks.find((t) => t.id === selected_task_id)
    if (task && task.default_run_config_id === null) {
      // Capture the task name before resetting selected_task_id
      task_name_for_dialog = task.name
      no_default_config_dialog?.show()
      // Reset selection since we can't proceed without a run config
      await tick()
      selected_task_id = null
      name = null
      description = ""
    }
  }

  $: task_options = data_loaded
    ? format_task_options(tasks, $run_configs_by_task_composite_id)
    : []
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
        value: task.id ?? "",
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
      const project_id = $page.params.project_id ?? ""
      const composite_key = get_task_composite_id(project_id, task.id ?? "")
      let run_config = run_configs[composite_key]?.find(
        (config) => config.id === task.default_run_config_id,
      )
      if (run_config != null) {
        return (
          (run_config.name ?? "") +
          ` | ${model_name(run_config.run_config_properties.model_name, $model_info)} (${provider_name_from_id(run_config.run_config_properties.model_provider_name)})` +
          ` | ${getRunConfigPromptDisplayName(run_config, $current_task_prompts)}`
        )
      } else {
        return ""
      }
    } else {
      return "⚠️ No default run config set"
    }
  }

  // TODO: Move this to a shared component since select_tasks_menu.svelte uses it too
  async function load_tasks(project_id: string) {
    if (!project_id) {
      tasks_loading_error = "No project selected"
      tasks = []
      return
    }
    try {
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
      tasks = tasks_data
    } catch (error) {
      tasks_loading_error = "Tasks failed to load: " + error
      tasks = []
    }
  }

  // Clear error when form fields change
  function clearErrorIfPresent() {
    if (error) {
      error = null
    }
  }

  async function add_kiln_task_tool() {
    try {
      clearErrorIfPresent()
      if (!selected_task_id) {
        error = createKilnError({
          message: "Please select a task.",
          status: 400,
        })
        return
      }

      const task = tasks.find((t) => t.id === selected_task_id)
      if (!task) {
        error = createKilnError({
          message: "Selected task not found.",
          status: 400,
        })
        return
      }

      await client.POST("/api/projects/{project_id}/add_kiln_task_tool", {
        params: {
          path: {
            project_id: $page.params.project_id,
          },
        },
        body: {
          name: name ?? "",
          description: description,
          task_id: selected_task_id || "",
          run_config_id: task.default_run_config_id || "",
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
    } finally {
      submitting = false
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
    {#if !tasks_loading_error}
      <FormContainer
        submit_label="Add"
        on:submit={add_kiln_task_tool}
        bind:error
        bind:submitting
      >
        <FormElement
          label="Kiln Task"
          bind:value={selected_task_id}
          id="task"
          inputType="fancy_select"
          fancy_select_options={task_options}
          disabled={!data_loaded}
          description="The task to add as a tool, using the task's current default run options."
          info_description="The task's default run options will be frozen in time for this task and won't update if you change the task's default run config later."
          on:change={clearErrorIfPresent}
        />

        {#if selected_task_id}
          <FormElement
            label="Kiln Task Tool Name"
            id="task_name"
            description="A unique short tool name such as 'research_agent'. Be descriptive about what role this tool is for."
            info_description="Must be in snake_case format. It should be descriptive of what the tool does as the model will see it. When adding multiple tools to a task each tool needs a unique name, so being unique and descriptive is important."
            bind:value={name}
            max_length={120}
            validator={validate_name}
            on:change={clearErrorIfPresent}
          />

          <FormElement
            label="Kiln Task Tool Description"
            inputType="textarea"
            id="task_description"
            description="A description for the model to understand what this tool can do, and when to use it."
            info_description="It should be descriptive of what the tool does as the model will see it. Example of a high quality description: 'Performs research on a topic using reasoning and tools to provide expert insights.'"
            bind:value={description}
            validator={validate_description}
            on:change={clearErrorIfPresent}
          />
        {/if}
      </FormContainer>
    {:else}
      <div class="text-sm text-error">
        {tasks_loading_error}
      </div>
    {/if}
  </div>
</div>

<Dialog
  bind:this={no_default_config_dialog}
  title="⚠️ No default run config set"
  subtitle={task_name_for_dialog
    ? `The task "${task_name_for_dialog}" doesn't have a default run config set. You need to set a default run config for the task before it can be added as a tool.`
    : "This task doesn't have a default run config set. You need to set a default run config for the task before it can be added as a tool."}
  action_buttons={[
    {
      label: "OK",
      isPrimary: true,
    },
  ]}
>
  <div class="flex flex-col gap-4">
    <p class="text-sm text-base-content/70">
      To add this task as a tool, you first need to:
    </p>
    <ol class="list-decimal list-inside text-sm text-base-content/70 space-y-2">
      <li>Go to the task's run page</li>
      <li>Configure the run options you want to use</li>
      <li>Set it as the default run config for the task</li>
      <li>Then return here to add it as a tool</li>
    </ol>
  </div>
</Dialog>
