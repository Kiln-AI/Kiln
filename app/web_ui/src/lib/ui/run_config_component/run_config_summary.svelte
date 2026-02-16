<script lang="ts">
  import type { TaskRunConfig } from "$lib/types"
  import { model_info, get_task_composite_id } from "$lib/stores"
  import { getDetailedModelName } from "$lib/utils/run_config_formatters"
  import { getRunConfigPromptDisplayName } from "$lib/utils/run_config_formatters"
  import { prompts_by_task_composite_id } from "$lib/stores/prompts_store"
  import { goto } from "$app/navigation"

  export let project_id: string
  export let task_id: string
  export let task_run_config: TaskRunConfig
  export let is_default: boolean = false

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  $: tools_count =
    task_run_config.run_config_properties.tools_config?.tools?.length ?? 0

  function openRunConfig() {
    goto(`/optimize/${project_id}/${task_id}/run_config/${task_run_config.id}`)
  }
</script>

<div
  class="cursor-pointer hover:bg-base-200 rounded-lg p-4"
  tabindex="0"
  aria-label="Open Run Configuration"
  role="button"
  on:click={openRunConfig}
  on:keydown={(e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      openRunConfig()
    }
  }}
>
  <div>
    <div class="flex items-center gap-2">
      <div class="font-medium">
        {task_run_config.name}
      </div>
      {#if is_default}
        <span class="badge badge-sm badge-primary badge-outline">
          Default
        </span>
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
  </div>
</div>
