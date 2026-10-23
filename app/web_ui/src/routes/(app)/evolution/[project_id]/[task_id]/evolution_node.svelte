<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { EvoNode } from "$lib/utils/evolution/graph_assembly"
  import type { NodeDisplay } from "$lib/utils/evolution/score_lens"
  import StarIcon from "$lib/ui/icons/star_icon.svelte"
  import EditIcon from "$lib/ui/icons/edit_icon.svelte"

  export let node: EvoNode
  export let display: NodeDisplay | undefined = undefined
  export let selected: boolean = false
  export let pinned: boolean = false

  const dispatch = createEventDispatcher<{
    select: string
    toggle_pin: string
  }>()

  // The strip is the same set of (eval, score key) cells on every card, so it
  // is laid out as one fixed-width block: 2px cells, 1px gaps, right-anchored.
  const CELL_W = 2
  const CELL_GAP = 1
  $: strip = display?.strip ?? []
  $: strip_width = Math.max(0, strip.length * (CELL_W + CELL_GAP) - CELL_GAP)
</script>

<div class="relative group w-[280px] h-[84px]">
  <button
    type="button"
    class="w-full h-full text-left rounded-lg border bg-white shadow-sm hover:shadow-md transition-shadow px-3 py-2 flex flex-col justify-between
      {selected ? 'ring-2 ring-primary' : ''}
      {node.ghost
      ? 'border-dashed border-gray-300 !bg-gray-50'
      : 'border-gray-200'}
      {display?.dimmed ? 'opacity-30' : ''}"
    on:click={() => dispatch("select", node.id)}
  >
    <div class="flex items-start gap-1 min-w-0 w-full">
      <span
        class="line-clamp-2 leading-tight text-sm font-medium min-w-0 {node.ghost
          ? 'text-gray-400 italic'
          : 'text-gray-900'}"
        title={node.name}
      >
        {node.name}
      </span>
      {#if node.starred}
        <span
          class="w-3.5 h-3.5 text-amber-500 flex-none mt-px"
          title="Starred"
        >
          <StarIcon filled={true} />
        </span>
      {/if}
      {#if node.origin === "agent"}
        <span
          class="text-[10px] uppercase tracking-wide text-gray-400 border border-gray-200 rounded px-1 flex-none"
          title="Created by an agent"
        >
          agent
        </span>
      {/if}
      {#if node.noteFull}
        <span
          class="w-3 h-3 text-gray-400 flex-none mt-0.5"
          title={node.noteSummary ?? "Has a provenance note"}
        >
          <EditIcon />
        </span>
      {/if}
      {#if display?.best}
        <span
          class="flex-none text-[10px] font-medium text-primary border border-primary/40 rounded-full px-1.5"
          title="Best under current lens"
        >
          Best
        </span>
      {/if}
    </div>
    <div
      class="text-xs text-gray-500 truncate w-full"
      title={node.ghost ? undefined : display?.subtitle ?? undefined}
    >
      {node.ghost ? "This run config was deleted" : display?.subtitle ?? ""}
    </div>
    <div class="flex items-center gap-1.5 w-full min-w-0">
      {#if !node.ghost}
        <!-- The lens value is optional now (see the Lens type): with no lens
             chosen the card shows what is true of the config without one. The
             run count is always here, whatever the lens, because it is what
             says whether a score is worth reading at all. -->
        {#if display?.lens_value != null}
          <span
            class="w-2.5 h-2.5 rounded-full flex-none"
            style="background-color: {display?.lens_color ?? '#d1d5db'}"
          ></span>
          <span class="text-xs font-medium text-gray-900 truncate">
            {display.lens_value}
          </span>
        {/if}
        <span
          class="text-xs flex-none {display?.runs
            ? 'text-gray-500'
            : 'text-gray-300'}"
          title={display?.runs
            ? `${display.runs} eval runs behind this config, in the selected split`
            : "No eval runs in the selected split"}
        >
          {display?.runs ?? 0} runs
        </span>
        {#if strip.length > 0}
          <span
            class="flex gap-px ml-auto flex-none overflow-hidden max-w-[200px]"
            style="width: {strip_width}px"
          >
            {#each strip as cell (cell.evalId + "::" + cell.scoreKey)}
              <span
                class="w-[2px] h-2 flex-none {cell.mode === 'absolute'
                  ? 'opacity-60'
                  : ''}"
                style="background-color: {cell.color}"
                title={cell.title}
              ></span>
            {/each}
          </span>
        {/if}
      {/if}
    </div>
  </button>
  {#if !node.ghost}
    <button
      type="button"
      class="absolute -top-1.5 -right-1.5 text-[10px] font-medium rounded-full px-1.5 py-0.5 border shadow-sm transition-opacity
        {pinned
        ? 'opacity-100 bg-primary text-primary-content border-primary'
        : 'opacity-0 group-hover:opacity-100 focus:opacity-100 bg-white text-gray-500 border-gray-300 hover:text-gray-900'}"
      title={pinned ? "Remove from compare set" : "Pin to compare"}
      on:click|stopPropagation={() => dispatch("toggle_pin", node.id)}
    >
      {pinned ? "Pinned" : "Pin"}
    </button>
  {/if}
</div>
