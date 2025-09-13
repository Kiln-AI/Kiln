<script lang="ts">
  import type { ToolCallMessageParam } from "$lib/types"

  export let tool_call: ToolCallMessageParam
</script>

<div>
  <div class="text-xs font-mono">
    Tool: {tool_call.function.name}
  </div>
  <div class="text-xs font-mono">
    Arguments: {tool_call.function.arguments}
  </div>
</div>
