<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import ToolSchemaViewer from "$lib/ui/tool_schema_viewer.svelte"
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
  import { selected_tool_for_task } from "$lib/stores/tools_store"

  $: project_id = $page.params.project_id!
  $: tool_id = $page.url.searchParams.get("tool_id")

  let selected_task_id: string | null = null
  let run_config_name = ""
  let tool_name: string | null = null
  let tool_input_schema: Record<string, unknown> | null = null
  let tool_output_schema: Record<string, unknown> | null = null
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
    load_tool_name()
  }

  $: if (tool_name && !run_config_name) {
    run_config_name = `MCP ${tool_name}`
  }
  $: tool_schema_ready =
    tool_name !== null &&
    (tool_input_schema !== null || tool_output_schema !== null)

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

  async function load_tool_name() {
    if (!tool_id) return
    try {
      const cached_tool = get(selected_tool_for_task)
      if (cached_tool?.name) {
        tool_name = cached_tool.name
        tool_input_schema =
          (cached_tool as { inputSchema?: Record<string, unknown> })
            .inputSchema ?? null
        tool_output_schema =
          (cached_tool as { outputSchema?: Record<string, unknown> })
            .outputSchema ?? null
        return
      }
      const parts = tool_id.split("::")
      if (parts.length < 4) {
        return
      }
      const tool_server_id = parts[2]
      const tool_name_part = parts.slice(3).join("::")
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tool_servers/{tool_server_id}",
        {
          params: { path: { project_id, tool_server_id } },
        },
      )
      if (fetch_error || !data?.available_tools) {
        return
      }
      const tool = data.available_tools.find(
        (available_tool) => available_tool.name === tool_name_part,
      )
      tool_name = tool?.name ?? tool_name_part
      tool_input_schema = (tool?.inputSchema as Record<string, unknown>) ?? null
      tool_output_schema =
        (tool?.outputSchema as Record<string, unknown>) ?? null
    } catch {
      // Ignore; prefill will fall back to null
    }
  }

  async function handle_save() {
    if (!tool_id || !selected_task_id) {
      error = createKilnError({ message: "Please select a task.", status: 400 })
      submitting = false
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
      if (!config.id) {
        throw new Error("Run config ID missing after save.")
      }
      if (make_default) {
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
      })
      goto(`/run?run_config_id=${encodeURIComponent(config.id)}`)
    } catch (err) {
      error = createKilnError(err)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Add MCP Tool As Run Config"
    subtitle="Allow one of your existing tasks to invoke this MCP tool directly, without a wrapper agent."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp#mcp-run-configs"
    breadcrumbs={[
      { label: "Settings", href: "/settings" },
      { label: "Manage Tools", href: `/settings/manage_tools/${project_id}` },
    ]}
  >
    {#if tool_missing}
      <div class="text-error">
        Tool data not available. Please start from the tool server page.
      </div>
    {:else if compatibility_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else}
      <div class="flex flex-col gap-4 mb-6">
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
                  ? `${incompatible_count} task${
                      incompatible_count === 1 ? "" : "s"
                    } aren't compatible with this tool because their input/output schema doesn't match.`
                  : `${incompatible_count} task${
                      incompatible_count === 1 ? "" : "s"
                    } aren't compatible with this tool because their input/output schema doesn't match.`}
                warning_color={no_compatible_tasks ? "error" : "warning"}
                large_icon={true}
                outline={true}
              />
              {#if no_compatible_tasks && tool_schema_ready}
                <details class="text-sm text-gray-600">
                  <summary class="cursor-pointer">View tool schema</summary>
                  <div class="mt-2">
                    <ToolSchemaViewer
                      inputSchema={tool_input_schema}
                      outputSchema={tool_output_schema}
                      inputTitle="Input"
                      outputTitle="Output"
                    />
                  </div>
                </details>
              {/if}
              {#if tool_id}
                <a
                  class="link text-sm text-gray-500"
                  href={`/settings/manage_tools/${project_id}/create_task_from_tool?tool_id=${encodeURIComponent(
                    tool_id,
                  )}`}
                >
                  Create a new task using this tool's schema
                </a>
              {/if}
            {/if}
            {#if !no_compatible_tasks}
              <div class="flex flex-col gap-6">
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
                  inputType="checkbox"
                  label="Make Default"
                  id="make_default"
                  bind:value={make_default}
                />
              </div>
              <Collapse title="Advanced">
                <FormElement
                  inputType="input"
                  label="Run Config Name"
                  id="run_config_name"
                  bind:value={run_config_name}
                  info_description="Run config names are names to help you identify a particular configuration for running a task. In this case, invoking this MCP tool."
                />
              </Collapse>
            {/if}
          </div>
        </FormContainer>
      </div>
    {/if}
  </AppPage>
</div>
