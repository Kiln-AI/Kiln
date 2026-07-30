<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { EvoNode } from "$lib/utils/evolution/graph_assembly"
  import type { NodeDisplay } from "$lib/utils/evolution/score_lens"
  import ChevronRightIcon from "$lib/ui/icons/chevron_right_icon.svelte"
  import EvolutionNode from "./evolution_node.svelte"

  // Expected sorted created_at desc (build_forest emits unlinkedIds that way)
  export let nodes: EvoNode[] = []
  export let displays: Record<string, NodeDisplay> = {}
  export let selected_id: string | null = null
  export let expanded: boolean = false
  export let collapsible: boolean = true
  export let pins: string[] = []

  const dispatch = createEventDispatcher<{
    select: string
    toggle: undefined
    toggle_pin: string
  }>()

  function month_label(created_at: string | null): string {
    if (!created_at) {
      return "Unknown date"
    }
    const date = new Date(created_at)
    if (isNaN(date.getTime())) {
      return "Unknown date"
    }
    return date.toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
    })
  }

  // Group into consecutive month buckets, preserving created_at-desc order
  $: month_groups = nodes.reduce(
    (groups: { label: string; nodes: EvoNode[] }[], node) => {
      const label = month_label(node.created_at)
      const last = groups[groups.length - 1]
      if (last && last.label === label) {
        last.nodes.push(node)
      } else {
        groups.push({ label, nodes: [node] })
      }
      return groups
    },
    [],
  )
</script>

{#if nodes.length > 0}
  <div class="mt-8">
    {#if collapsible}
      <button
        type="button"
        class="flex items-center gap-2 text-sm font-medium text-gray-900"
        on:click={() => dispatch("toggle")}
      >
        <span
          class="w-4 h-4 block text-gray-500 transition-transform {expanded
            ? 'rotate-90'
            : ''}"
        >
          <ChevronRightIcon />
        </span>
        Unlinked run configs ({nodes.length})
      </button>
    {:else}
      <div class="text-sm font-medium text-gray-900">
        Unlinked run configs ({nodes.length})
      </div>
    {/if}

    {#if expanded || !collapsible}
      {#each month_groups as group (group.label)}
        <div
          class="text-xs font-medium text-gray-500 uppercase tracking-wide mt-4 mb-2"
        >
          {group.label}
        </div>
        <div
          class="grid grid-cols-[repeat(auto-fill,minmax(280px,max-content))] gap-3"
        >
          {#each group.nodes as node (node.id)}
            <EvolutionNode
              {node}
              display={displays[node.id]}
              selected={selected_id === node.id}
              pinned={pins.includes(node.id)}
              on:select={(event) => dispatch("select", event.detail)}
              on:toggle_pin={(event) => dispatch("toggle_pin", event.detail)}
            />
          {/each}
        </div>
      {/each}
    {/if}
  </div>
{/if}
