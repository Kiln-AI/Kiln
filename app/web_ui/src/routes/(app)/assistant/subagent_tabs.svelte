<script lang="ts">
  import {
    subagent_store,
    visibleSubagentTabs,
    shouldCollapseSubagentTabs,
    type SubAgentItem,
  } from "$lib/chat/subagent_store"
  import Dialog from "$lib/ui/dialog.svelte"
  import SubagentStatusDot from "./subagent_status_dot.svelte"

  const children = subagent_store.children
  const selectedId = subagent_store.selectedId

  // Only running children keep a tab, plus the selected child even when
  // terminal (so the view isn't yanked while reading); selecting away drops
  // the terminal tab. Above the overflow limit the child tabs collapse into a
  // single "N agents running" chip — except the selected child, which stays as
  // its own tab so you can see where you are.
  $: visibleChildren = visibleSubagentTabs($children, $selectedId)
  $: collapsed = shouldCollapseSubagentTabs(visibleChildren)
  $: selectedChildTab = collapsed
    ? visibleChildren.find((c) => c.subagent_id === $selectedId) ?? null
    : null
  $: tabChildren = collapsed
    ? selectedChildTab
      ? [selectedChildTab]
      : []
    : visibleChildren
  $: runningCount = visibleChildren.filter((c) => c.status === "running").length

  let pickerDialog: Dialog | null = null

  function statusLabel(status: SubAgentItem["status"]): string {
    switch (status) {
      case "running":
        return "running"
      case "completed":
        return "completed"
      case "failed":
        return "failed"
      case "stopped":
        return "stopped"
      case "timeout":
        return "timed out"
    }
  }

  function select(id: string | null): void {
    subagent_store.select(id)
  }

  function stopChild(id: string): void {
    void subagent_store.stop(id)
  }

  function openPicker(): void {
    pickerDialog?.show()
  }

  function pickFromDialog(id: string): void {
    subagent_store.select(id)
    pickerDialog?.close()
  }
</script>

{#if visibleChildren.length > 0}
  <div
    class="flex-none flex flex-wrap items-center gap-1.5 pt-2 px-1 w-full md:max-w-3xl md:mx-auto"
    role="tablist"
    aria-label="Agents"
  >
    <button
      type="button"
      role="tab"
      aria-selected={$selectedId === null}
      class="btn btn-xs {$selectedId === null
        ? 'btn-neutral'
        : 'btn-ghost text-base-content/60'}"
      on:click={() => select(null)}
    >
      Main
    </button>
    {#each tabChildren as child (child.subagent_id)}
      <div class="group relative">
        <button
          type="button"
          role="tab"
          aria-selected={$selectedId === child.subagent_id}
          class="btn btn-xs gap-1.5 {$selectedId === child.subagent_id
            ? 'btn-neutral'
            : 'btn-ghost text-base-content/60'}"
          on:click={() => select(child.subagent_id)}
          title="{child.name} ({child.agent_type}) — {statusLabel(
            child.status,
          )}"
        >
          <SubagentStatusDot status={child.status} />
          <span class="max-w-[10rem] truncate normal-case">{child.name}</span>
        </button>
        {#if child.status === "running"}
          <button
            type="button"
            class="absolute -right-1 -top-1 hidden group-hover:flex items-center justify-center size-4 rounded-full bg-base-300 text-base-content/60 hover:bg-error/20 hover:text-error text-[10px] leading-none"
            on:click|stopPropagation={() => stopChild(child.subagent_id)}
            title="Stop this sub-agent"
            aria-label="Stop {child.name}"
          >
            ×
          </button>
        {/if}
      </div>
    {/each}
    {#if collapsed}
      <button
        type="button"
        class="btn btn-xs btn-ghost gap-1.5 text-base-content/60"
        on:click={openPicker}
        title="Show all sub-agents"
      >
        <SubagentStatusDot status="running" />
        <span class="normal-case">
          {runningCount} agent{runningCount === 1 ? "" : "s"} running
        </span>
      </button>
    {/if}
  </div>
{/if}

<Dialog bind:this={pickerDialog} title="Sub-agents" action_buttons={[]}>
  <div class="max-h-[min(50vh,420px)] overflow-y-auto -mx-1 px-1">
    <div class="flex flex-col gap-0.5">
      {#each visibleChildren as child (child.subagent_id)}
        <button
          type="button"
          class="flex items-center gap-2 w-full rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-base-200/80"
          on:click={() => pickFromDialog(child.subagent_id)}
        >
          <SubagentStatusDot status={child.status} />
          <span class="flex-1 min-w-0 truncate text-sm font-medium"
            >{child.name}</span
          >
          <span
            class="shrink-0 rounded-full bg-base-content/[0.06] px-2 py-0.5 text-[10px] text-base-content/60"
            >{child.agent_type}</span
          >
          <span class="shrink-0 text-xs text-base-content/50"
            >{statusLabel(child.status)}</span
          >
          <span class="shrink-0 text-xs text-base-content/40 whitespace-nowrap"
            >{child.rounds_used} round{child.rounds_used === 1 ? "" : "s"}</span
          >
        </button>
      {/each}
    </div>
  </div>
</Dialog>
