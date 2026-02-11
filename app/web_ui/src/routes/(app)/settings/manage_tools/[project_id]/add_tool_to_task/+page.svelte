<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { onDestroy, onMount } from "svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type { components } from "$lib/api_schema"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import { ui_state } from "$lib/stores"
  import { get } from "svelte/store"
  import {
    save_new_mcp_run_config,
    update_task_default_run_config,
  } from "$lib/stores/run_configs_store"
  import { selected_tool_for_task } from "$lib/stores/tool_store"

  $: project_id = $page.params.project_id!
  $: tool_id = $page.url.searchParams.get("tool_id")

  let selected_task_id: string | null = null
  let run_config_name = ""
  let make_default = false
  let submitting = false
  let saved = false
  let error: KilnError | null = null

  let tool_loading_error: KilnError | null = null
  type TaskToolCompatibility = components["schemas"]["TaskToolCompatibility"]

  let compatibility_tasks: TaskToolCompatibility[] = []
  let compatibility_loading = false
  let compatibility_error: string | null = null

  onMount(async () => {
    const cached_tool = get(selected_tool_for_task)
    if (!tool_id) {
      tool_loading_error = createKilnError(
        new Error("No tool selected. Please start from the tool server page."),
      )
    } else if (!cached_tool) {
      tool_loading_error = createKilnError(
        new Error(
          "Tool data not available. Please start from the tool server page.",
        ),
      )
    }
    if (tool_id) {
      await load_compatibility_tasks()
    }
  })

  onDestroy(() => {
    selected_tool_for_task.set(null)
  })

  $: compatible_task_options = [
    {
      label: "Compatible Tasks",
      options: compatibility_tasks
        .filter((task) => task.compatible)
        .map((task) => ({
          label: task.task_name,
          value: task.task_id,
        })),
    },
  ] as OptionGroup[]

  $: incompatible_count = compatibility_tasks.filter(
    (t) => !t.compatible,
  ).length

  async function load_compatibility_tasks() {
    if (!tool_id) {
      compatibility_error = "Tool not selected."
      return
    }
    compatibility_loading = true
    compatibility_error = null
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks_compatible_with_tool",
        {
          params: { path: { project_id }, query: { tool_id } },
        },
      )
      if (fetch_error) {
        compatibility_error = "Failed to load tasks: " + fetch_error
      } else {
        compatibility_tasks = data
      }
    } finally {
      compatibility_loading = false
    }
  }

  async function handle_save() {
    if (!tool_id) {
      error = createKilnError({ message: "Tool not selected.", status: 400 })
      return
    }
    if (!selected_task_id) {
      error = createKilnError({ message: "Please select a task.", status: 400 })
      return
    }
    const task_id = selected_task_id

    submitting = true
    saved = false
    error = null
    try {
      const config = await save_new_mcp_run_config(
        project_id,
        task_id,
        tool_id,
        run_config_name || undefined,
      )
      if (make_default) {
        if (!config.id) {
          throw new Error("Run config ID missing after save.")
        }
        await update_task_default_run_config(project_id, task_id, config.id)
      }
      ui_state.set({
        ...get(ui_state),
        current_task_id: task_id,
        current_project_id: project_id,
        pending_run_config_id: config.id,
      })
      goto("/run")
    } catch (err) {
      error = createKilnError(err)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Run Tool Directly on Task"
    breadcrumbs={[
      { label: "Settings", href: "/settings" },
      { label: "Manage Tools", href: `/settings/manage_tools/${project_id}` },
    ]}
  >
    {#if tool_loading_error}
      <div class="text-error">
        {tool_loading_error.getMessage() ||
          "Tool data not available. Please start from the tool server page."}
      </div>
    {:else}
      <div class="flex flex-col gap-4 mb-6">
        <p class="text-sm text-gray-500">
          This will call the MCP tool directly with task inputs — no wrapping
          agent or prompt is used.
        </p>
        <FormContainer
          submit_label="Save"
          on:submit={handle_save}
          bind:error
          bind:submitting
          bind:saved
        >
          <div class="flex flex-col gap-4">
            {#if incompatible_count > 0}
              <Warning
                warning_message="{incompatible_count} task{incompatible_count ===
                1
                  ? ''
                  : 's'} not available — schema doesn't match this tool. Create a new task, update the MCP tool schema, or use the agent option instead."
                warning_color="warning"
                large_icon={true}
                outline={true}
              />
            {/if}
            <FormElement
              inputType="fancy_select"
              label="Select a Task"
              id="task_id"
              bind:value={selected_task_id}
              fancy_select_options={compatible_task_options}
              disabled={compatibility_loading}
              empty_state_message={compatibility_loading
                ? "Loading tasks..."
                : "No compatible tasks found"}
            />
            {#if compatibility_error}
              <div class="text-error text-sm">{compatibility_error}</div>
            {/if}
            <FormElement
              inputType="input"
              label="Run Config Name"
              id="run_config_name"
              bind:value={run_config_name}
              optional={true}
              placeholder="Auto-generated if empty"
            />
            <FormElement
              inputType="checkbox"
              label="Make Default"
              id="make_default"
              bind:value={make_default}
            />
          </div>
        </FormContainer>
      </div>
    {/if}
  </AppPage>
</div>
