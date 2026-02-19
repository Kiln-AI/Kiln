<script lang="ts">
  import type { TaskRunConfig } from "$lib/types"
  import { available_tools } from "$lib/stores"
  import { get_tool_server_name } from "$lib/stores/tools_store"
  import { tool_link } from "$lib/utils/link_builder"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"

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

  $: properties = [
    {
      name: "MCP Tool",
      value: mcp_tool_name,
      link: tool_server_link || undefined,
      tooltip: `This run configuration will invoke the MCP tool "${mcp_tool_name}" directly, without any wrapper agent.`,
    },
    ...(tool_server_name
      ? [{ name: "Tool Server", value: tool_server_name }]
      : []),
  ] as UiProperty[]
</script>

<PropertyList {properties} />
