<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import type { Task } from "$lib/types"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import Dialog from "$lib/ui/dialog.svelte"
  import { load_task_run_configs } from "$lib/stores/run_configs_store"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import {
    load_available_models,
    load_available_prompts,
    load_model_info,
    uncache_available_tools,
  } from "$lib/stores"
  import RunOptionsDropdown from "../../../../../run/run_options_dropdown.svelte"
  import AvailableModelsDropdown from "../../../../../run/available_models_dropdown.svelte"
  import PromptTypeSelector from "../../../../../run/prompt_type_selector.svelte"
  import ToolsSelector from "../../../../../run/tools_selector.svelte"
  import AdvancedRunOptions from "../../../../../run/advanced_run_options.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import type { RunConfigProperties, StructuredOutputMode } from "$lib/types"
  import type { components } from "$lib/api_schema"
  import { save_new_task_run_config } from "$lib/stores/run_configs_store"

  let error: KilnError | null = null
  let submitting = false
  let name: string | null = null
  let description = ""
  let selected_task_id: string | null = null
  let selected_run_config_id: string | "custom" | null = null
  let tasks: Task[] = []
  let tasks_loading_error: string | null = null
  let data_loaded = false

  // Modal for creating new run config
  let create_run_config_dialog: Dialog | null = null
  let create_run_config_error: KilnError | null = null
  let new_run_config_model_name = ""
  let new_run_config_provider_name:
    | components["schemas"]["ModelProviderName"]
    | "" = ""
  let new_run_config_prompt_method = "simple_prompt_builder"
  let new_run_config_tools: string[] = []
  let new_run_config_temperature = 1.0
  let new_run_config_top_p = 1.0
  let new_run_config_structured_output_mode: StructuredOutputMode = "default"
  let previous_run_config_id: string | "custom" | null = null

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

  $: if (selected_task_id && name === null) {
    // Only set name if it's null (initial selection)
    const task = tasks.find((t) => t.id === selected_task_id)
    if (task) {
      name = to_snake_case(task.name)
    }
  }

  // Load run configs when task is selected
  $: if (selected_task_id && $page.params.project_id) {
    load_task_run_configs($page.params.project_id, selected_task_id)
    // Only reset run config selection if it's not already set to a valid value
    if (
      selected_run_config_id === null ||
      selected_run_config_id === "custom"
    ) {
      selected_run_config_id = default_run_config_id
    }
  }

  // Get the default run config ID for the selected task
  $: default_run_config_id = (() => {
    if (selected_task_id) {
      const task = tasks.find((t) => t.id === selected_task_id)
      return task?.default_run_config_id || null
    }
    return null
  })()

  // Track previous selection for cancel functionality
  $: if (
    selected_run_config_id &&
    selected_run_config_id !== "__create_new_run_config__"
  ) {
    previous_run_config_id = selected_run_config_id
  }

  // Handle special case when "Create New Run Configuration" is selected
  $: if (selected_run_config_id === "__create_new_run_config__") {
    show_create_run_config_modal()
    // Reset the selection after showing modal
    selected_run_config_id = null
  }

  // Handle cloning - if we have a pre-filled name from URL params, modify it
  $: if (name && $page.url.search.includes("name=")) {
    // This is a clone operation, modify the name to indicate it's a copy
    if (!name.startsWith("copy_of_")) {
      name = `copy_of_${name}`
    }
  }

  $: task_options = data_loaded ? format_task_options(tasks) : []
  function format_task_options(tasks: Task[]): OptionGroup[] {
    if (tasks.length === 0) {
      return []
    }
    let option_groups: OptionGroup[] = []
    option_groups.push({
      options: tasks.map((task) => ({
        label: `${task.name} (ID: ${task.id})`,
        value: task.id ?? "",
      })),
    })
    return option_groups
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

  // Functions for creating new run config
  function show_create_run_config_modal() {
    create_run_config_error = null
    new_run_config_model_name = ""
    new_run_config_provider_name = ""
    new_run_config_prompt_method = "simple_prompt_builder"
    new_run_config_tools = []
    new_run_config_temperature = 1.0
    new_run_config_top_p = 1.0
    new_run_config_structured_output_mode = "default"

    // Ensure dialog is properly bound before showing
    if (create_run_config_dialog) {
      create_run_config_dialog.show()
    } else {
      console.error("create_run_config_dialog is not bound")
    }
  }

  async function cancel_create_run_config(): Promise<boolean> {
    // Restore the previous selection
    await tick()
    // Use a timeout to ensure the restoration happens after all reactive statements
    setTimeout(() => {
      selected_run_config_id = previous_run_config_id
      previous_run_config_id = null
    }, 0)
    await tick()
    return true
  }

  async function create_new_run_config(): Promise<boolean> {
    create_run_config_error = null

    if (!new_run_config_model_name || !new_run_config_provider_name) {
      create_run_config_error = createKilnError({
        message: "Model selection is required.",
        status: 400,
      })
      return false
    }

    if (!selected_task_id || !$page.params.project_id) {
      create_run_config_error = createKilnError({
        message: "No task selected.",
        status: 400,
      })
      return false
    }

    try {
      const run_config_properties: RunConfigProperties = {
        model_name: new_run_config_model_name,
        model_provider_name: new_run_config_provider_name,
        prompt_id: new_run_config_prompt_method,
        temperature: new_run_config_temperature,
        top_p: new_run_config_top_p,
        structured_output_mode: new_run_config_structured_output_mode,
        tools_config: {
          tools: new_run_config_tools,
        },
      }

      const new_config = await save_new_task_run_config(
        $page.params.project_id,
        selected_task_id,
        run_config_properties,
      )

      // Select the newly created run config
      selected_run_config_id = new_config.id ?? ""

      return true
    } catch (e) {
      create_run_config_error = createKilnError(e)
      return false
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

      if (!selected_run_config_id) {
        error = createKilnError({
          message: "Please select a run configuration.",
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
          run_config_id: selected_run_config_id,
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
          description="The task to add as a tool."
          info_description="Select the task that will be used as a tool."
          on:change={clearErrorIfPresent}
        />

        {#if selected_task_id}
          <RunOptionsDropdown
            bind:selected_run_config_id
            {default_run_config_id}
            task_id={selected_task_id}
            project_id={$page.params.project_id}
            show_create_new_option={true}
            label="Run Configuration"
            description="The run configuration to use for task calls when using this tool."
          />
        {/if}

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
  bind:this={create_run_config_dialog}
  title="Create New Run Configuration"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
      asyncAction: cancel_create_run_config,
    },
    {
      label: "Create",
      isPrimary: true,
      asyncAction: create_new_run_config,
    },
  ]}
>
  <div class="flex flex-col gap-4">
    <AvailableModelsDropdown
      bind:model_name={new_run_config_model_name}
      bind:provider_name={new_run_config_provider_name}
    />

    <PromptTypeSelector bind:prompt_method={new_run_config_prompt_method} />

    {#if selected_task_id}
      <ToolsSelector
        bind:tools={new_run_config_tools}
        project_id={$page.params.project_id}
        task_id={selected_task_id}
      />
    {/if}

    <Collapse title="Advanced Options">
      <AdvancedRunOptions
        bind:temperature={new_run_config_temperature}
        bind:top_p={new_run_config_top_p}
        bind:structured_output_mode={new_run_config_structured_output_mode}
        has_structured_output={false}
      />
    </Collapse>

    {#if create_run_config_error}
      <div class="text-error text-sm">
        {create_run_config_error.getMessage() || "An unknown error occurred"}
      </div>
    {/if}
  </div>
</Dialog>
