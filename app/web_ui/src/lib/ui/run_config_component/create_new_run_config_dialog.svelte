<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import RunConfigComponent from "./run_config_component.svelte"
  import type { Task, TaskRunConfig } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { generate_memorable_name } from "$lib/utils/name_generator"

  export let subtitle: string | null = null
  export let project_id: string
  export let task: Task | null
  export let new_run_config_created:
    | ((run_config: TaskRunConfig) => void)
    | null = null
  export let hide_tools_selector: boolean = false
  export let model: string | undefined = undefined

  type DialogMode = "create" | "clone"
  let mode: DialogMode = "create"
  let source_run_config: TaskRunConfig | null = null

  let submitting: boolean
  let save_config_error: KilnError | null = null
  let run_config_component: RunConfigComponent | null = null
  let run_config_name: string = generate_memorable_name()
  let dialog: Dialog | null = null

  $: dialog_title =
    mode === "create"
      ? "Create New Run Configuration"
      : "Clone Run Configuration"

  export function show() {
    mode = "create"
    source_run_config = null
    save_config_error = null
    run_config_name = generate_memorable_name()
    dialog?.show()
  }

  export function showClone(run_config: TaskRunConfig) {
    mode = "clone"
    source_run_config = run_config
    save_config_error = null
    run_config_name = generate_memorable_name()
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
        new_run_config_created?.(saved_run_config)
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

<Dialog bind:this={dialog} title={dialog_title} {subtitle} on:close>
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
          requires_structured_output={!!task.output_json_schema}
          tools_selector_settings={{
            hide_create_kiln_task_tool_button: true,
          }}
          {hide_tools_selector}
          {model}
          {run_config_name}
          selected_run_config_id={source_run_config?.id || null}
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
