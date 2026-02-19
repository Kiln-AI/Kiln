<script lang="ts">
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import ToolSchemaViewer from "$lib/ui/tool_schema_viewer.svelte"
  import { onDestroy, onMount } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { get } from "svelte/store"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import { ui_state } from "$lib/stores"
  import { selected_tool_for_task } from "$lib/stores/tools_store"
  import type { ExternalToolApiDescription } from "$lib/types"

  $: project_id = $page.params.project_id!
  $: tool_id = $page.url.searchParams.get("tool_id")

  let tool: ExternalToolApiDescription | null = null
  let loading_error: KilnError | null = null
  let task_name = ""
  let instruction = ""
  let submitting = false
  let saved = false
  let form_error: KilnError | null = null

  onMount(async () => {
    const cached_tool = get(selected_tool_for_task)
    if (!tool_id) {
      loading_error = createKilnError(
        new Error("No tool selected. Please start from the tool server page."),
      )
      return
    }

    if (cached_tool) {
      tool = cached_tool
      task_name = cached_tool.name
      instruction = cached_tool.description?.trim() || instruction
      return
    }

    // Fallback: fetch tool data by tool_id (e.g., on refresh or direct link)
    try {
      const parts = tool_id.split("::")
      if (parts.length < 4) {
        throw new Error("Invalid tool ID.")
      }
      const tool_server_id = parts[2]
      const tool_name = parts.slice(3).join("::")
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tool_servers/{tool_server_id}",
        {
          params: { path: { project_id, tool_server_id } },
        },
      )
      if (error || !data) {
        throw new Error("Failed to load tool server.")
      }
      const matched_tool = data.available_tools?.find(
        (available_tool) => available_tool.name === tool_name,
      )
      if (!matched_tool) {
        throw new Error("Tool data not available.")
      }
      tool = matched_tool
      task_name = matched_tool.name
      instruction = matched_tool.description?.trim() || instruction
    } catch (err) {
      loading_error = createKilnError(err)
    }
  })

  onDestroy(() => {
    selected_tool_for_task.set(null)
  })

  async function handle_save() {
    if (!tool_id) {
      form_error = createKilnError({
        message: "Tool not selected.",
        status: 400,
      })
      return
    }
    if (!task_name.trim()) {
      form_error = createKilnError({
        message: "Task name is required.",
        status: 400,
      })
      return
    }
    if (!instruction.trim()) {
      form_error = createKilnError({
        message: "Instruction is required.",
        status: 400,
      })
      return
    }

    submitting = true
    saved = false
    form_error = null

    try {
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/create_task_from_tool",
        {
          params: { path: { project_id } },
          body: { tool_id, task_name, instruction },
        },
      )
      if (error) {
        throw error
      }
      if (!data?.id) {
        throw new Error("Task ID missing after create.")
      }
      ui_state.set({
        ...get(ui_state),
        current_task_id: data.id,
        current_project_id: project_id,
      })
      goto("/run")
    } catch (err) {
      form_error = createKilnError(err)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="New task from tool"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp/running-tools-as-tasks"
    breadcrumbs={[
      { label: "Settings", href: "/settings" },
      { label: "Manage Tools", href: `/settings/manage_tools/${project_id}` },
    ]}
  >
    {#if loading_error}
      <div class="text-error">
        {loading_error.getMessage() || "Failed to load tool details."}
      </div>
    {:else if tool}
      <FormContainer
        submit_label="Create Task"
        on:submit={handle_save}
        bind:error={form_error}
        bind:submitting
        bind:saved
      >
        <FormElement
          inputType="input"
          label="Task Name"
          id="task_name"
          bind:value={task_name}
        />
        <div>
          <div class="text-sm font-medium mb-2">Tool Schema</div>
          <ToolSchemaViewer
            inputSchema={tool.inputSchema}
            outputSchema={tool.outputSchema}
            inputTitle="Input Schema (From Tool)"
            outputTitle="Output Schema (From Tool)"
          />
        </div>
        <Collapse title="Advanced">
          <FormElement
            inputType="textarea"
            label="Prompt / Task Instructions"
            id="instruction"
            height="medium"
            bind:value={instruction}
            description="By default, we'll call the selected MCP tool directly—no prompt required. We'll use this prompt if you later add a model-based agent to this task."
            info_description={`You're creating a task from an MCP tool, so by default we'll call the MCP tool directly when you invoke this task.
However, in the future you may choose to add other ways of invoking this task later, such as an agent. For that case, we need a prompt describing the task for the agent to follow.
This prompt won't be used unless you add agent-based task run configurations.`}
          />
        </Collapse>
      </FormContainer>
    {/if}
  </AppPage>
</div>
