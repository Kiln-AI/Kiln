<script lang="ts">
  import type { TaskRunConfig } from "$lib/types"
  import { model_info } from "$lib/stores"
  import { getDetailedModelName } from "$lib/utils/run_config_formatters"
  import { getRunConfigPromptDisplayName } from "$lib/utils/run_config_formatters"
  import { current_task_prompts } from "$lib/stores"
  import RunConfigDetailsDialog from "./run_config_details_dialog.svelte"

  export let project_id: string
  export let task_id: string
  export let task_run_config: TaskRunConfig
  export let is_default: boolean = false

  let details_dialog: RunConfigDetailsDialog | null = null
  let clickable_element: HTMLDivElement | null = null
  let opened_by_click = false

  function open_details_dialog() {
    details_dialog?.show()
  }

  function handle_dialog_close() {
    // Blur if opened by click to prevent focus returning
    if (opened_by_click && clickable_element) {
      clickable_element.blur()
    }
    opened_by_click = false
  }

  $: tools_count =
    task_run_config.run_config_properties.tools_config?.tools?.length ?? 0
</script>

<div
  bind:this={clickable_element}
  class="rounded-md p-2 cursor-pointer hover:bg-base-200 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-base-300"
  on:click={() => {
    opened_by_click = true
    open_details_dialog()
  }}
  on:keydown={(e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      opened_by_click = false
      open_details_dialog()
    }
  }}
  role="button"
  tabindex="0"
  aria-label="Open run configuration details"
>
  <div class="flex items-center gap-2">
    <div class="font-medium">
      {task_run_config.name}
    </div>
    {#if is_default}
      <span class="badge badge-sm badge-primary badge-outline"> Default </span>
    {/if}
  </div>
  <div class="text-sm text-gray-500">
    <div>
      Model: {getDetailedModelName(task_run_config, $model_info)}
    </div>
    <div>
      Prompt: {getRunConfigPromptDisplayName(
        task_run_config,
        $current_task_prompts,
      )}
    </div>
    <div>
      Tools: {tools_count > 0 ? `${tools_count} available` : "None"}
    </div>
  </div>
</div>

<RunConfigDetailsDialog
  bind:this={details_dialog}
  {task_run_config}
  {project_id}
  {task_id}
  on:close={handle_dialog_close}
/>
