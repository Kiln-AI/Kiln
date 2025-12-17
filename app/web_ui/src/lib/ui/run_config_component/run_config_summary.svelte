<script lang="ts">
  import type { TaskRunConfig } from "$lib/types"
  import { model_info, get_task_composite_id } from "$lib/stores"
  import { getDetailedModelName } from "$lib/utils/run_config_formatters"
  import { getRunConfigPromptDisplayName } from "$lib/utils/run_config_formatters"
  import { prompts_by_task_composite_id } from "$lib/stores/prompts_store"
  import RunConfigDetailsDialog from "./run_config_details_dialog.svelte"

  export let project_id: string
  export let task_id: string
  export let task_run_config: TaskRunConfig
  export let is_default: boolean = false

  let details_dialog: RunConfigDetailsDialog | null = null

  function open_details_dialog() {
    details_dialog?.show()
  }

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  $: tools_count =
    task_run_config.run_config_properties.tools_config?.tools?.length ?? 0
</script>

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
    Prompt: {getRunConfigPromptDisplayName(task_run_config, task_prompts)}
  </div>
  <div>
    Tools: {tools_count > 0 ? `${tools_count} available` : "None"}
  </div>
</div>
<button
  class="link text-sm text-gray-500 hover:text-gray-700 mt-1"
  on:click={open_details_dialog}
>
  See Details
</button>

<RunConfigDetailsDialog
  bind:this={details_dialog}
  {task_run_config}
  {project_id}
  {task_id}
/>
