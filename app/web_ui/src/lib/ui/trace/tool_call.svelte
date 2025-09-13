<script lang="ts">
  import type { ToolCallMessageParam } from "$lib/types"
  import Output from "../../../routes/(app)/run/output.svelte"

  export let tool_call: ToolCallMessageParam
  export let nameTag: string = "Tool Name"
</script>

<div class="grid grid-cols-[auto,1fr] gap-x-3 gap-y-0 text-xs">
  <div class="font-medium text-gray-500">{nameTag}:</div>
  <div class="font-mono">{tool_call.function.name}</div>
  <div class="font-medium text-gray-500">Arguments:</div>
  <Output raw_output={tool_call.function.arguments} no_padding={true} />
</div>
