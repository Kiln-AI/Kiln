<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import type { Task } from "$lib/types"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import Dialog from "$lib/ui/dialog.svelte"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { uncache_available_tools } from "$lib/stores"
  import SavedRunConfigurationsDropdown from "$lib/ui/run_config_component/saved_run_configs_dropdown.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import type { RunConfigProperties } from "$lib/types"
  import { save_new_task_run_config } from "$lib/stores/run_configs_store"
  import type { components } from "$lib/api_schema"

  let error: KilnError | null = null
  let submitting = false
  let name: string | null = null
  let description = ""
  let selected_task_id: string | null = null
  let selected_run_config_id: string | null = null

  // Modal for creating new run config
  let create_run_config_dialog: Dialog | null = null
  let create_run_config_error: KilnError | null = null

  $: project_id = $page.params.project_id
  $: selected_task = tasks.find((t) => t.id === selected_task_id)

  onMount(async () => {
    await load_tasks($page.params.project_id ?? "")

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

  $: if (selected_task && name === null) {
    name = to_snake_case(selected_task.name)
  }

  $: task_options = data_loaded ? create_task_options(tasks) : []

  function create_task_options(tasks: Task[]): OptionGroup[] {
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

  let tasks: Task[] = []
  let tasks_loading_error: string | null = null
  let data_loaded = false

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

  let should_show_create_modal = false

  // Handle special case when "Create New Run Configuration" is selected
  $: if (selected_run_config_id === "__create_new_run_config__") {
    should_show_create_modal = true
    selected_run_config_id = null
  }

  // Show modal when flag is set
  $: if (should_show_create_modal) {
    should_show_create_modal = false
    show_create_new_run_config_modal()
  }

  function show_create_new_run_config_modal() {
    create_run_config_error = null
    if (create_run_config_dialog) {
      create_run_config_dialog.show()
    }
  }

  async function cancel_create_run_config(): Promise<boolean> {
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
        model_provider_name:
          new_run_config_provider_name as components["schemas"]["ModelProviderName"],
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

  // Clear error when form fields change
  function clear_error_if_present() {
    if (error) {
      error = null
    }
  }

  async function add_kiln_task_tool() {
    try {
      clear_error_if_present()
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
          on:change={clear_error_if_present}
        />

        {#if selected_task}
          <SavedRunConfigurationsDropdown
            {project_id}
            current_task={selected_task}
            bind:selected_run_config_id
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
            on:change={clear_error_if_present}
          />

          <FormElement
            label="Kiln Task Tool Description"
            inputType="textarea"
            id="task_description"
            description="A description for the model to understand what this tool can do, and when to use it."
            info_description="It should be descriptive of what the tool does as the model will see it. Example of a high quality description: 'Performs research on a topic using reasoning and tools to provide expert insights.'"
            bind:value={description}
            validator={validate_description}
            on:change={clear_error_if_present}
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
      label: "Save",
      isPrimary: true,
      asyncAction: create_new_run_config,
    },
  ]}
>
  <div class="flex flex-col gap-4">
    {#if selected_task}
      <RunConfigComponent
        {project_id}
        current_task={selected_task}
        bind:selected_run_config_id
      />
    {/if}

    {#if create_run_config_error}
      <div class="text-error text-sm">
        {create_run_config_error.getMessage() || "An unknown error occurred"}
      </div>
    {/if}
  </div>
</Dialog>
