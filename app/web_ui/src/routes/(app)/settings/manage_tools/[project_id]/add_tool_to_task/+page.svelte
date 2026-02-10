<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { onDestroy, onMount } from "svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type { Task } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import { ui_state } from "$lib/stores"
  import { get } from "svelte/store"
  import {
    save_new_mcp_run_config,
    update_task_default_run_config,
  } from "$lib/stores/run_configs_store"
  import { tools_store, tools_store_initialized } from "$lib/stores/tools_store"
  import { selected_tool_for_task } from "$lib/stores/tool_store"

  $: project_id = $page.params.project_id!
  $: tool_id = $page.url.searchParams.get("tool_id")

  let selected_option: "agent" | "direct" | null = null
  let selected_task_id: string | null = null
  let selected_task_id_agent: string | null = null
  let run_config_name = ""
  let make_default = false
  let submitting = false
  let saved = false
  let error: KilnError | null = null

  let tasks: Task[] = []
  let tasks_loading_error: string | null = null
  let data_loaded = false

  let tool_loading_error: KilnError | null = null

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

    const { data, error: fetch_error } = await client.GET(
      "/api/projects/{project_id}/tasks",
      { params: { path: { project_id } } },
    )
    if (fetch_error) {
      tasks_loading_error = "Tasks failed to load: " + fetch_error
    } else {
      tasks = data
    }
    data_loaded = true
  })

  onDestroy(() => {
    selected_tool_for_task.set(null)
  })

  $: task_options = data_loaded
    ? ([
        {
          label: "Project Tasks",
          options: tasks.map((task) => ({
            label: task.name,
            value: task.id ?? "",
            description: task.description || undefined,
          })),
        },
      ] as OptionGroup[])
    : []

  function toggle_option(option: "agent" | "direct") {
    selected_option = selected_option === option ? null : option
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
      })
      goto("/run")
    } catch (err) {
      error = createKilnError(err)
    } finally {
      submitting = false
    }
  }

  async function handle_agent_go_to_run() {
    if (!tool_id) {
      error = createKilnError({ message: "Tool not selected.", status: 400 })
      return
    }
    if (!selected_task_id_agent) {
      error = createKilnError({ message: "Please select a task.", status: 400 })
      return
    }
    const task_id = selected_task_id_agent
    await tools_store_initialized
    tools_store.update((state) => {
      const existing = state.selected_tool_ids_by_task_id[task_id]
      const next = existing?.includes(tool_id)
        ? existing
        : [...(existing ?? []), tool_id]
      return {
        ...state,
        selected_tool_ids_by_task_id: {
          ...state.selected_tool_ids_by_task_id,
          [task_id]: next,
        },
      }
    })
    ui_state.set({
      ...get(ui_state),
      current_task_id: task_id,
      current_project_id: project_id,
      pending_tool_id: tool_id,
    })
    goto("/run")
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Add Tool to Task"
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
        <div
          class="card border transition-all duration-200 hover:shadow-md hover:border-primary cursor-pointer"
          on:click={() => toggle_option("agent")}
          on:keydown={(e) => {
            if (e.key === "Enter" || e.key === " ") toggle_option("agent")
          }}
          tabindex="0"
          role="button"
        >
          <div class="card-body p-4">
            <div class="text-lg font-semibold">
              Give Kiln Agent Access to This Tool
            </div>
            <div class="text-sm text-gray-500">
              A Kiln AI agent will use the model you choose and can call this
              MCP tool during task execution.
            </div>
          </div>
        </div>
        {#if selected_option === "agent"}
          <div class="pl-2">
            <FormElement
              inputType="fancy_select"
              label="Select a Task"
              id="agent_task_id"
              bind:value={selected_task_id_agent}
              fancy_select_options={task_options}
              disabled={!data_loaded}
              empty_state_message="Loading tasks..."
            />
            {#if tasks_loading_error}
              <div class="text-error text-sm mt-2">{tasks_loading_error}</div>
            {/if}
            <div class="text-sm text-gray-500 mt-2">
              The tool will be pre-added to your run configuration. Choose a
              model and prompt on the Run page.
            </div>
            <button
              class="btn btn-primary btn-sm mt-4"
              type="button"
              on:click={handle_agent_go_to_run}
            >
              Go to Run Page
            </button>
          </div>
        {/if}
        <div
          class="card border transition-all duration-200 hover:shadow-md hover:border-primary cursor-pointer"
          on:click={() => toggle_option("direct")}
          on:keydown={(e) => {
            if (e.key === "Enter" || e.key === " ") toggle_option("direct")
          }}
          tabindex="0"
          role="button"
        >
          <div class="card-body p-4">
            <div class="text-lg font-semibold">
              Task Calls MCP Directly (No Agent)
            </div>
            <div class="text-sm text-gray-500">
              Kiln will call your MCP tool directly with task inputs and
              retrieve task outputs. No wrapper agent or prompt is used.
            </div>
          </div>
        </div>
        {#if selected_option === "direct"}
          <FormContainer
            submit_label="Save"
            on:submit={handle_save}
            bind:error
            bind:submitting
            bind:saved
          >
            <Warning
              warning_message="Some tasks may not be available because their schemas don't match this tool."
              warning_color="warning"
              large_icon={true}
              outline={true}
            />
            <FormElement
              inputType="fancy_select"
              label="Select a Task"
              id="task_id"
              bind:value={selected_task_id}
              fancy_select_options={task_options}
              disabled={!data_loaded}
              empty_state_message="Loading tasks..."
            />
            {#if tasks_loading_error}
              <div class="text-error text-sm mt-2">{tasks_loading_error}</div>
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
          </FormContainer>
        {/if}
      </div>
    {/if}
  </AppPage>
</div>
