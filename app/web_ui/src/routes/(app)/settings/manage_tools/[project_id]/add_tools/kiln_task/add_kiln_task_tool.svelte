<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import type { Task } from "$lib/types"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import Dialog from "$lib/ui/dialog.svelte"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { uncache_available_tools } from "$lib/stores"
  import SavedRunConfigurationsDropdown from "$lib/ui/run_config_component/saved_run_configs_dropdown.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import { tool_name_validator } from "$lib/utils/input_validators"

  let error: KilnError | null = null
  let submitting = false
  let name: string = ""
  let description = ""
  let selected_task_id: string | null = null
  let selected_run_config_id: string | null = null
  let loading = false

  // Modal for creating new run config
  let create_run_config_dialog: Dialog | null = null
  let save_config_error: KilnError | null = null
  let run_config_component: RunConfigComponent | null = null

  $: project_id = $page.params.project_id

  let selected_task: Task | null = null
  $: selected_task = tasks.find((t) => t.id === selected_task_id) || null

  onMount(async () => {
    await load_tasks($page.params.project_id ?? "")

    // Check for URL parameters to pre-fill form (for cloning)
    const url_params = new URLSearchParams($page.url.search)
    const clone_name = url_params.get("name")
    const clone_description = url_params.get("description")
    const clone_task_id = url_params.get("task_id")
    const clone_run_config_id = url_params.get("run_config_id")
    if (clone_task_id) {
      selected_task_id = clone_task_id
    }
    // Wait for reactive statements so we can update name to the clone name
    await tick()
    if (clone_name) {
      name = clone_name
    }
    if (clone_run_config_id) {
      selected_run_config_id = clone_run_config_id
    }
    if (clone_description) {
      description = clone_description
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

  $: if (selected_task) {
    name = to_snake_case(selected_task.name)
  }

  $: task_options = data_loaded ? create_task_options(tasks) : []

  function create_task_options(tasks: Task[]): OptionGroup[] {
    if (tasks.length === 0) {
      return []
    }
    let option_groups: OptionGroup[] = []
    option_groups.push({
      label: "",
      options: [
        {
          label: "New Kiln Task",
          value: "__create_new_kiln_task__",
          badge: "＋",
          badge_color: "primary",
        },
      ],
    })
    option_groups.push({
      label: "Project Tasks",
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

  // Show the create dialog when the user clicks the create new button
  $: if (selected_run_config_id === "__create_new_run_config__") {
    save_config_error = null
    create_run_config_dialog?.show()
  } else {
    save_config_error = null
    create_run_config_dialog?.close()
  }

  $: if (selected_task_id === "__create_new_kiln_task__") {
    goto(`/settings/create_task/${project_id}`)
  }

  async function create_new_run_config() {
    loading = true
    if (run_config_component) {
      await run_config_component.save_new_run_config()
    }
    loading = false
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

      if (!name) {
        error = createKilnError({
          message: "Please enter a tool name.",
          status: 400,
        })
        return
      }

      if (!description) {
        error = createKilnError({
          message: "Please enter a tool description.",
          status: 400,
        })
        return
      }

      await client.POST("/api/projects/{project_id}/kiln_task_tool", {
        params: {
          path: {
            project_id: $page.params.project_id,
          },
        },
        body: {
          name: name,
          description: description,
          task_id: selected_task_id,
          run_config_id: selected_run_config_id,
          is_archived: false,
        },
      })

      // Delete the project_id from the available_tools, so next load it loads the updated list.
      uncache_available_tools($page.params.project_id)
      // Navigate to the manage tools page for the created tool
      goto(`/settings/manage_tools/${$page.params.project_id}/kiln_task_tools`)
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
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
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if !tasks_loading_error}
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
          description="The Kiln task the tool will call."
          on:change={clear_error_if_present}
        />

        {#if selected_task}
          <SavedRunConfigurationsDropdown
            {project_id}
            current_task={selected_task}
            bind:selected_run_config_id
            run_page={false}
            description="A configuration defining options the Kiln task will use when called, such as the model and prompt."
          />
          <FormElement
            label="Tool Name"
            id="task_name"
            description="A unique short tool name such as 'web_researcher'. Be descriptive about what this task does."
            info_description="Must be in snake_case format. It should be descriptive of what the tool does as the model will see it. When adding multiple tools to a task each tool needs a unique name, so being unique and descriptive is important."
            bind:value={name}
            max_length={128}
            validator={tool_name_validator}
            on:change={clear_error_if_present}
          />

          <FormElement
            label="Tool Description"
            inputType="textarea"
            id="task_description"
            description="A description for the model to understand what this task does, and when to use it."
            info_description="It should be descriptive of what the task does as the model will see it. Example of a high quality description: 'Performs research on a topic using reasoning and access to the web to provide expert insights.'"
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
  title="Run Configuration"
  on:close={() => {
    create_run_config_dialog?.close()
    if (selected_run_config_id === "__create_new_run_config__") {
      selected_run_config_id = null
    }
  }}
>
  <FormContainer
    submit_visible={true}
    submit_label="Create"
    on:submit={create_new_run_config}
    {error}
    gap={4}
    bind:submitting={loading}
    keyboard_submit={false}
  >
    <div class="flex flex-col gap-4">
      {#if selected_task}
        <RunConfigComponent
          bind:this={run_config_component}
          {project_id}
          bind:selected_run_config_id
          current_task={selected_task}
          hide_create_kiln_task_tool_button={true}
          {save_config_error}
        />
      {/if}

      {#if save_config_error}
        <div class="text-error text-sm">
          {save_config_error.getMessage() || "An unknown error occurred"}
        </div>
      {/if}
    </div>
  </FormContainer>
</Dialog>
