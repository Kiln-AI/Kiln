<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { EvoNode } from "$lib/utils/evolution/graph_assembly"
  import type { NodeDisplay } from "$lib/utils/evolution/score_lens"

  export let node: EvoNode
  export let display: NodeDisplay | undefined = undefined
  export let selected: boolean = false

  const dispatch = createEventDispatcher<{ select: string }>()
</script>

<button
  type="button"
  class="w-[200px] h-[76px] text-left rounded-lg border bg-white shadow-sm hover:shadow-md transition-shadow px-3 py-2 flex flex-col justify-between
    {selected ? 'ring-2 ring-primary' : ''}
    {node.ghost
    ? 'border-dashed border-gray-300 !bg-gray-50'
    : 'border-gray-200'}
    {display?.dimmed ? 'opacity-30' : ''}"
  on:click={() => dispatch("select", node.id)}
>
  <div class="flex items-center gap-1 min-w-0 w-full">
    <span
      class="truncate text-sm font-medium {node.ghost
        ? 'text-gray-400 italic'
        : 'text-gray-900'}"
    >
      {node.name}
    </span>
    {#if node.starred}
      <span class="text-amber-500 text-xs flex-none" title="Starred">★</span>
    {/if}
    {#if node.origin === "human"}
      <span class="text-[10px] flex-none" title="Created by a human">🧑</span>
    {:else if node.origin === "agent"}
      <span class="text-[10px] flex-none" title="Created by an agent">🤖</span>
    {/if}
    {#if node.noteFull}
      <span
        class="text-gray-400 text-xs flex-none"
        title={node.noteSummary ?? "Has a provenance note"}
      >
        ✎
      </span>
    {/if}
    {#if display?.best}
      <span
        class="flex-none text-[10px] leading-none bg-amber-100 border border-amber-300 rounded-full px-1 py-0.5"
        title="Best under current lens"
      >
        👑
      </span>
    {/if}
  </div>
  <div class="text-xs text-gray-500 truncate w-full">
    {node.ghost ? "This run config was deleted" : display?.subtitle ?? ""}
  </div>
  <div class="flex items-center gap-1.5 w-full min-w-0">
    {#if !node.ghost}
      <span
        class="w-2.5 h-2.5 rounded-full flex-none"
        style="background-color: {display?.lens_color ?? '#d1d5db'}"
      ></span>
      <span class="text-xs font-medium text-gray-900">
        {display?.lens_value ?? "—"}
      </span>
      {#if display && display.strip_colors.length > 0}
        <span class="flex gap-px ml-auto overflow-hidden flex-none">
          {#each display.strip_colors as color}
            <span
              class="w-[2px] h-2 flex-none"
              style="background-color: {color}"
            ></span>
          {/each}
        </span>
      {/if}
    {/if}
  </div>
</button>
