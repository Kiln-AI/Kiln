<script lang="ts">
  import { load_task } from "$lib/stores"
  import type { Task } from "$lib/types"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { goto } from "$app/navigation"
  import Output from "$lib/ui/output.svelte"

  interface PromptInfo {
    id: string
    name: string
    prompt: string
  }

  // Passing in both prompt info and model info at the same time will have unexpected behavior.
  export let prompt_info: PromptInfo | undefined = undefined
  export let model: string | undefined = undefined // e.g. "openrouter/gpt_5_nano"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let loading = false
  let loading_error: KilnError | null = null
  let task: Task | null = null

  let run_config_component: RunConfigComponent | null = null
  let save_config_error: KilnError | null = null
  let submitting = false

  onMount(async () => {
    loading = true
    try {
      task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Task not found")
      }
    } catch (e) {
      loading_error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  async function create_run_config() {
    submitting = true
    try {
      save_config_error = null
      const saved_config = await run_config_component?.save_new_run_config()
      if (!saved_config) {
        throw new Error("Failed to save run config")
      }
      goto(`/optimize/${project_id}/${task_id}`)
    } catch (e) {
      save_config_error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create Run Configuration"
    subtitle="Create a new run configuration for your task{prompt_info
      ? ' with your new prompt'
      : model
        ? ' with your selected model'
        : ''}."
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div class="text-error text-sm">
        {loading_error?.getMessage() || "An unknown error occurred"}
      </div>
    {:else if task}
      <FormContainer
        submit_label="Create"
        on:submit={create_run_config}
        error={save_config_error}
        bind:submitting
      >
        <div class="flex flex-col gap-4">
          {#if prompt_info}
            <div class="flex flex-col gap-2">
              <div class="flex flex-row gap-2 justify-between">
                <div class="text-sm font-medium">Prompt</div>
                <div class="flex flex-row gap-4">
                  <div class="text-sm text-gray-500">{prompt_info.name}</div>
                  <div class="text-sm text-gray-500">ID: {prompt_info.id}</div>
                </div>
              </div>
              <Output raw_output={prompt_info.prompt} />
            </div>
          {/if}
          <RunConfigComponent
            bind:this={run_config_component}
            {project_id}
            current_task={task}
            requires_structured_output={!!task.output_json_schema}
            tools_selector_settings={{
              hide_create_kiln_task_tool_button: true,
            }}
            hide_prompt_selector={!!prompt_info}
            {model}
            disable_model_selection={!!model}
          />
        </div>
      </FormContainer>
    {/if}
  </AppPage>
</div>
