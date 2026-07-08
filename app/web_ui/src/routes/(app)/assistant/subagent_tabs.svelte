<script lang="ts">
  import {
    subagent_store,
    isTerminalSubagentStatus,
    type SubAgentItem,
  } from "$lib/chat/subagent_store"
  import BrailleSpinner from "./braille_spinner.svelte"

  const children = subagent_store.children
  const selectedId = subagent_store.selectedId

  function statusGlyph(status: SubAgentItem["status"]): string {
    switch (status) {
      case "completed":
        return "✓"
      case "failed":
      case "stopped":
        return "✕"
      case "timeout":
        return "⏱"
      default:
        return ""
    }
  }

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
</script>

{#if $children.length > 0}
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
    {#each $children as child (child.subagent_id)}
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
          {#if child.status === "running"}
            <BrailleSpinner />
          {:else if isTerminalSubagentStatus(child.status)}
            <span
              class="inline-block w-3 text-center {child.status === 'completed'
                ? ''
                : 'text-error/70'}"
              aria-hidden="true">{statusGlyph(child.status)}</span
            >
          {/if}
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
  </div>
{/if}
