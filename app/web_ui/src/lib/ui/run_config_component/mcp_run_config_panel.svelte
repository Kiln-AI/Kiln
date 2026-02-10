<script lang="ts">
  import Output from "$lib/ui/output.svelte"
  import type { TaskRunConfig } from "$lib/types"

  export let run_config: TaskRunConfig

  $: mcp_tool = run_config.run_config_properties.mcp_tool
  $: mcp_tool_name = mcp_tool?.tool_name ?? "Unknown"
  $: input_schema_output = mcp_tool?.input_schema
    ? JSON.stringify(mcp_tool.input_schema, null, 2)
    : "Input Format: Plain text"
  $: output_schema_output = mcp_tool?.output_schema
    ? JSON.stringify(mcp_tool.output_schema, null, 2)
    : "Output Format: Plain text"
</script>

<div class="flex flex-col gap-4">
  <div>
    <div class="text-sm font-medium mb-2">MCP Tool Name</div>
    <div class="text-sm text-gray-500">{mcp_tool_name}</div>
  </div>
  <div>
    <div class="text-sm font-medium mb-2">Input Schema</div>
    <Output raw_output={input_schema_output} />
  </div>
  <div>
    <div class="text-sm font-medium mb-2">Output Schema</div>
    <Output raw_output={output_schema_output} />
  </div>
</div>
