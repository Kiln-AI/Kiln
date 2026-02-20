<script lang="ts">
  import type { TaskRunConfig } from "$lib/types"
  import { isKilnAgentRunConfig, isMcpRunConfig } from "$lib/types"
  import { model_info, get_task_composite_id } from "$lib/stores"
  import { getRunConfigModelDisplayName } from "$lib/utils/run_config_formatters"
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

  $: mcp_props = isMcpRunConfig(task_run_config.run_config_properties)
    ? task_run_config.run_config_properties
    : null
  $: kiln_props = isKilnAgentRunConfig(task_run_config.run_config_properties)
    ? task_run_config.run_config_properties
    : null
  $: is_mcp = mcp_props !== null
  $: tools_count = kiln_props?.tools_config?.tools?.length ?? 0

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
  <div class="flex items-center gap-2">
    <div class="font-medium">
      {task_run_config.name}
    </div>
    {#if is_default}
      <span class="badge badge-sm badge-primary badge-outline"> Default </span>
    {/if}
  </div>
  <div class="text-sm text-gray-500">
    {#if is_mcp}
      <div>Type: MCP Tool (No Agent)</div>
      <div>
        Tool: {mcp_props?.tool_reference?.tool_name ?? "Unknown"}
      </div>
    {:else}
      <div>
        Model: {getRunConfigModelDisplayName(task_run_config, $model_info)}
      </div>
      <div>
        Prompt: {getRunConfigPromptDisplayName(task_run_config, task_prompts)}
      </div>
      <div>
        Tools: {tools_count > 0 ? `${tools_count} available` : "None"}
      </div>
    {/if}
  </div>
</div>
