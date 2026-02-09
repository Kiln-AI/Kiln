<script lang="ts">
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Output from "$lib/ui/output.svelte"
  import { onDestroy, onMount } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { get } from "svelte/store"
  import {
    selected_tool_for_task,
    type ExternalToolApiDescription,
  } from "$lib/stores/tool_store"

  $: project_id = $page.params.project_id!
  $: tool_id = $page.url.searchParams.get("tool_id")

  let tool: ExternalToolApiDescription | null = null
  let loading_error: KilnError | null = null
  let task_name = ""
  let submitting = false
  let saved = false
  let form_error: KilnError | null = null

  onMount(() => {
    const cached_tool = get(selected_tool_for_task)
    if (!tool_id) {
      loading_error = createKilnError(
        new Error("No tool selected. Please start from the tool server page."),
      )
    } else if (!cached_tool) {
      loading_error = createKilnError(
        new Error(
          "Tool data not available. Please start from the tool server page.",
        ),
      )
    } else {
      tool = cached_tool
      task_name = cached_tool.name
    }
  })

  onDestroy(() => {
    selected_tool_for_task.set(null)
  })

  async function handle_save() {
    if (!tool_id) {
      return
    }

    submitting = true
    saved = false
    form_error = null

    // TODO: Wire to POST /api/projects/{project_id}/create_task_from_tool

    submitting = false
  }

  $: input_schema_output = tool?.inputSchema
    ? JSON.stringify(tool.inputSchema, null, 2)
    : "Input Format: Plain text"
  $: output_schema_output = tool?.outputSchema
    ? JSON.stringify(tool.outputSchema, null, 2)
    : "Output Format: Plain text"
</script>

<div class="max-w-[900px]">
  <AppPage
    title="New Task from Tool"
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
        <div class="mt-6">
          <div class="text-sm font-medium mb-2">Input Schema (from tool)</div>
          <Output raw_output={input_schema_output} />
        </div>
        <div class="mt-6">
          <div class="text-sm font-medium mb-2">Output Schema (from tool)</div>
          <Output raw_output={output_schema_output} />
        </div>
      </FormContainer>
    {/if}
  </AppPage>
</div>
