<script lang="ts">
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import type { TaskRunConfig } from "$lib/types"
  import { available_tools } from "$lib/stores"
  import { get_tool_server_name } from "$lib/stores/tools_store"
  import { tool_link } from "$lib/utils/link_builder"

  export let run_config: TaskRunConfig
  export let project_id: string

  $: mcp_tool = run_config.run_config_properties.mcp_tool
  $: mcp_tool_name = mcp_tool?.tool_name ?? "Unknown"
  $: tool_id = mcp_tool?.tool_id
  $: tool_server_link = tool_id ? tool_link(project_id, tool_id) : null
  $: tool_server_name = get_tool_server_name(
    $available_tools,
    project_id,
    tool_id,
  )
</script>

<div class="flex flex-col gap-4">
  <div>
    <div class="text-sm font-medium mb-2 flex items-center gap-1">
      MCP Tool
      <InfoTooltip
        tooltip_text={`This run configuration will invoke the MCP tool "${mcp_tool_name}" directly, without any wrapper agent.`}
      />
    </div>
    {#if tool_server_link}
      <a href={tool_server_link} class="text-sm text-gray-500 link">
        {mcp_tool_name}
      </a>
    {:else}
      <div class="text-sm text-gray-500">{mcp_tool_name}</div>
    {/if}
  </div>
  {#if tool_server_name}
    <div>
      <div class="text-sm font-medium mb-2">Tool Server</div>
      <div class="text-sm text-gray-500">{tool_server_name}</div>
    </div>
  {/if}
</div>
