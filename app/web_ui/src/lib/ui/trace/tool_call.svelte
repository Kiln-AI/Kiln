<script lang="ts">
  import type { ToolCallMessageParam } from "$lib/types"
  import Output from "../../../routes/(app)/run/output.svelte"
  import { dataset_item_link } from "$lib/utils/link_builder"

  export let tool_call: ToolCallMessageParam
  export let nameTag: string = "Tool Name"

  // Parse tool call result to extract task run information
  $: tool_info = (() => {
    return {
      task_run_id: "",
      task_id: "",
      project_id: "",
    }
  })()

  let dataset_link: string | null = null
  $: if (tool_info) {
    dataset_link = dataset_item_link(
      tool_info.project_id || "",
      tool_info.task_id || "",
      tool_info.task_run_id || "",
    )
  }
</script>

<div class="grid grid-cols-[auto,1fr] gap-x-3 gap-y-0 text-xs">
  <div class="font-medium text-gray-500">{nameTag}:</div>
  <div class="font-mono">{tool_call.function.name}</div>
  <div class="font-medium text-gray-500">Arguments:</div>
  <Output raw_output={tool_call.function.arguments} no_padding={true} />
  {#if dataset_link}
    <div class="font-medium text-gray-500">Subtask run:</div>
    <div>
      <a
        href={dataset_link}
        class="text-blue-600 hover:text-blue-800 underline"
        target="_blank"
        rel="noopener noreferrer"
      >
        View in Dataset
      </a>
    </div>
  {/if}
</div>
