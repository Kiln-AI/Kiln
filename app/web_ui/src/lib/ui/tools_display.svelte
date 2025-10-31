<script lang="ts">
  import { get_tools_property_info } from "$lib/stores/tools_store"
  import type { ToolSetApiDescription } from "$lib/types"

  export let tool_ids: string[] = []
  export let project_id: string
  export let available_tools: Record<string, ToolSetApiDescription[]>
  export let text_size: "xs" | "sm" = "sm"
  export let center_text: boolean = false

  $: tools_info = get_tools_property_info(tool_ids, project_id, available_tools)
  $: text_size_class = text_size === "xs" ? "text-xs" : "text-sm"
  $: badge_size_class = text_size === "xs" ? "badge-sm text-xs" : ""
</script>

<div class="text-gray-500 {text_size_class}">
  {#if Array.isArray(tools_info.value) && tools_info.value.length > 0}
    <div
      class="flex flex-wrap items-center gap-1 {center_text
        ? 'justify-center'
        : ''}"
    >
      <span>Available Tools:</span>
      {#each tools_info.value as tool_name, i}
        {@const link = tools_info.links?.[i]}
        {#if link}
          <a href={link} class="badge badge-outline {badge_size_class}">
            {tool_name}
          </a>
        {:else}
          <span class="badge badge-outline {badge_size_class}">
            {tool_name}
          </span>
        {/if}
      {/each}
    </div>
  {:else}
    <span class={center_text ? "block text-center" : ""}
      >Available Tools: {tools_info.value}</span
    >
  {/if}
</div>
