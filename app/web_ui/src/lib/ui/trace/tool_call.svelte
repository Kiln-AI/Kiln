<script lang="ts">
  import type { ToolCallMessageParam } from "$lib/types"
  import Output from "../../../routes/(app)/run/output.svelte"

  export let tool_call: ToolCallMessageParam
  export let nameTag: string = "Tool Name"
  export let project_id: string | undefined = undefined
  export let persistent_tool_id: string | undefined = undefined

  function get_tool_link(): string | null {
    if (!project_id) return null

    // If we have a persistent_tool_id, try to create a specific link
    if (persistent_tool_id) {
      // For Kiln task tools, extract tool_server_id from the persistent_tool_id
      // Kiln task tool IDs have format: "kiln_task::{tool_server_id}"
      if (persistent_tool_id.startsWith("kiln_task::")) {
        const tool_server_id = persistent_tool_id.substring(
          "kiln_task::".length,
        )
        return `/settings/manage_tools/${project_id}/kiln_task/${tool_server_id}`
      }
    }

    return null
  }
</script>

<div class="grid grid-cols-[auto,1fr] gap-x-3 gap-y-0 text-xs">
  <div class="font-medium text-gray-500">{nameTag}:</div>
  <div class="font-mono">
    {#if get_tool_link()}
      <a href={get_tool_link()} class="text-primary link" target="_blank">
        {tool_call.function.name}
      </a>
    {:else}
      {tool_call.function.name}
    {/if}
  </div>
  <div class="font-medium text-gray-500">Arguments:</div>
  <Output raw_output={tool_call.function.arguments} no_padding={true} />
</div>
