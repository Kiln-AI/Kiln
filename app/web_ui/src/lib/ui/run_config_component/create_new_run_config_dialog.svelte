<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import RunConfigComponent from "./run_config_component.svelte"
  import type { Task, TaskRunConfig } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"

  export let subtitle: string | null = null
  export let project_id: string
  export let task: Task | null
  export let new_run_config_created: (run_config: TaskRunConfig) => void

  let submitting: boolean
  let save_config_error: KilnError | null = null
  let run_config_component: RunConfigComponent | null = null
  let dialog: Dialog | null = null

  export function show() {
    save_config_error = null
    dialog?.show()
  }

  export function close() {
    save_config_error = null
    dialog?.close()
  }

  async function create_new_run_config() {
    submitting = true
    try {
      save_config_error = null
      const saved_run_config = await run_config_component?.save_new_run_config()
      if (saved_run_config) {
        new_run_config_created(saved_run_config)
        close() // Only close on success
      } else {
        throw new Error("Resulting saved run config not found.")
      }
    } catch (e) {
      save_config_error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title="Create New Run Configuration"
  {subtitle}
  on:close
>
  <FormContainer
    submit_visible={true}
    submit_label="Create"
    on:submit={create_new_run_config}
    gap={4}
    bind:submitting
    keyboard_submit={false}
  >
    <div class="flex flex-col gap-4">
      {#if task}
        <RunConfigComponent
          bind:this={run_config_component}
          {project_id}
          current_task={task}
          hide_create_kiln_task_tool_button={true}
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
