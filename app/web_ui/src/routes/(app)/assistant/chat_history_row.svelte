<script lang="ts">
  import { formatDate } from "$lib/utils/formatters"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import type { SessionListItem } from "$lib/chat/session_grouping"

  export let row: SessionListItem
  export let loading = false
  export let deleting = false
  export let busy = false
  export let onSelect: (row: SessionListItem) => void
  export let onDelete: (sessionId: string) => void

  function displayTitle(item: SessionListItem): string {
    if (item.title) return item.title
    return item.id.length > 12 ? `${item.id.slice(0, 10)}…` : item.id
  }
</script>

<div
  class="group relative flex items-center w-full rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-base-200/80 cursor-pointer"
  class:opacity-50={deleting}
  role="button"
  tabindex="0"
  on:click={() => !busy && onSelect(row)}
  on:keydown={(e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      if (!busy) onSelect(row)
    }
  }}
>
  <div class="flex flex-1 min-w-0 items-center gap-2">
    {#if row.auto_active}
      <span
        class="auto-dot size-2 shrink-0 rounded-full bg-primary"
        title="Auto mode is running"
        aria-label="Auto mode running"
        role="img"
      ></span>
    {/if}
    <span class="block text-sm font-medium truncate">{displayTitle(row)}</span>
  </div>
  {#if loading || deleting}
    <span class="loading loading-spinner loading-xs shrink-0 ml-2"></span>
  {:else}
    {#if row.auto_active}
      <span
        class="text-xs text-primary font-medium shrink-0 ml-3 whitespace-nowrap"
        >Working…</span
      >
    {:else if row.updated_at}
      <span class="text-xs text-gray-500 shrink-0 ml-3 whitespace-nowrap"
        >{formatDate(row.updated_at)}</span
      >
    {/if}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
      on:click|stopPropagation
    >
      <TableActionMenu
        width="w-40"
        items={[
          {
            label: "Delete",
            onclick: () => onDelete(row.id),
          },
        ]}
      />
    </div>
  {/if}
</div>

<style>
  .auto-dot {
    animation: auto-dot-pulse 1.6s ease-in-out infinite;
  }

  @keyframes auto-dot-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.4;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .auto-dot {
      animation: none;
    }
  }
</style>
