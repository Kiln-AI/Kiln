<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { onDestroy } from "svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type { TaskToolCompatibility } from "$lib/types"
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
  let error: KilnError | null = null

  let compatibility_tasks: TaskToolCompatibility[] = []
  let compatibility_loading = false
  let loaded_tool_id: string | null = null

  $: tool_missing = !tool_id

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
  $: no_compatible_tasks =
    compatibility_tasks.length > 0 &&
    incompatible_count === compatibility_tasks.length

  $: if (tool_id && tool_id !== loaded_tool_id && !compatibility_loading) {
    load_compatibility_tasks()
  }

  onDestroy(() => {
    selected_tool_for_task.set(null)
  })

  async function load_compatibility_tasks() {
    if (!tool_id) return

    compatibility_loading = true
    error = null
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks_compatible_with_tool",
        {
          params: { path: { project_id }, query: { tool_id } },
        },
      )
      if (fetch_error) {
        error = createKilnError({
          message: "Failed to load tasks",
          status: 500,
        })
        loaded_tool_id = tool_id
      } else {
        compatibility_tasks = data
        loaded_tool_id = tool_id
      }
    } catch (err) {
      error = createKilnError(err)
      loaded_tool_id = tool_id
    } finally {
      compatibility_loading = false
    }
  }

  async function handle_save() {
    if (!tool_id || !selected_task_id) {
      error = createKilnError({ message: "Please select a task.", status: 400 })
      return
    }

    submitting = true
    error = null
    try {
      const config = await save_new_mcp_run_config(
        project_id,
        selected_task_id,
        tool_id,
        run_config_name || undefined,
      )
      if (make_default) {
        if (!config.id) {
          throw new Error("Run config ID missing after save.")
        }
        await update_task_default_run_config(
          project_id,
          selected_task_id,
          config.id,
        )
      }
      ui_state.set({
        ...get(ui_state),
        current_task_id: selected_task_id,
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
    title="Run tool directly on a task"
    breadcrumbs={[
      { label: "Settings", href: "/settings" },
      { label: "Manage Tools", href: `/settings/manage_tools/${project_id}` },
    ]}
  >
    {#if tool_missing}
      <div class="text-error">
        Tool data not available. Please start from the tool server page.
      </div>
    {:else}
      <div class="flex flex-col gap-4 mb-6">
        <p class="text-sm text-gray-500">
          Runs the MCP tool directly with task inputs. No agent or prompt is
          used.
        </p>
        <FormContainer
          submit_label="Save"
          on:submit={handle_save}
          bind:error
          bind:submitting
          submit_disabled={submitting || no_compatible_tasks}
        >
          <div class="flex flex-col gap-4">
            {#if incompatible_count > 0}
              <Warning
                warning_message={no_compatible_tasks
                  ? `All ${incompatible_count} task${
                      incompatible_count === 1 ? "" : "s"
                    } are incompatible. Input and output schemas must match. Create a task from this tool instead.`
                  : `${incompatible_count} task${
                      incompatible_count === 1 ? "" : "s"
                    } are incompatible. Input and output schemas must match.`}
                warning_color="warning"
                large_icon={true}
                outline={true}
              />
              {#if tool_id}
                <a
                  class="btn btn-outline btn-sm w-full"
                  href={`/settings/manage_tools/${project_id}/create_task_from_tool?tool_id=${encodeURIComponent(
                    tool_id,
                  )}`}
                >
                  Create task from this tool
                </a>
              {/if}
            {/if}
            <div
              class="flex flex-col gap-6 {no_compatible_tasks
                ? 'opacity-60 pointer-events-none'
                : ''}"
            >
              <FormElement
                inputType="fancy_select"
                label="Select a Task"
                id="task_id"
                bind:value={selected_task_id}
                fancy_select_options={compatible_task_options}
                disabled={compatibility_loading || no_compatible_tasks}
                empty_state_message={compatibility_loading
                  ? "Loading tasks..."
                  : "No compatible tasks found"}
              />
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
          </div>
        </FormContainer>
      </div>
    {/if}
  </AppPage>
</div>
