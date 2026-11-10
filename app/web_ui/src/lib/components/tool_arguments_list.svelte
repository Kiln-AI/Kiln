<script lang="ts">
  import { format_tool_arguments } from "$lib/utils/tool_arguments"

  export let input_schema: unknown

  $: args = format_tool_arguments(input_schema)
</script>

{#if args.length > 0}
  <div class="divide-y divide-y-[0.5px]">
    {#each args as arg}
      <div class="py-2">
        <div class="flex flex-row gap-3 items-center">
          <span class="font-mono">{arg.name}</span>
          <span class="font-mono font-light text-gray-500">{arg.type} </span>
          {#if !arg.is_required}
            <span class="badge badge-sm badge-outline">Optional</span>
          {/if}
        </div>
        {#if arg.description}
          <div class="text-gray-500 text-sm mt-1">
            <span class="whitespace-pre-line break-words"
              >{arg.description}</span
            >
          </div>
        {/if}
      </div>
    {/each}
  </div>
{:else}
  <span class="text-gray-500">None</span>
{/if}
