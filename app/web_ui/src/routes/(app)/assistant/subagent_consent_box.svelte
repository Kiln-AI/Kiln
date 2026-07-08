<script lang="ts">
  export let name: string = ""
  export let agentType: string = ""
  export let prompt: string = ""
  export let onRun: () => void
  export let onSkip: () => void

  // Collapse long briefings so the consent box stays scannable.
  const PROMPT_COLLAPSE_LENGTH = 280
  let promptExpanded = false
  $: promptIsLong = prompt.length > PROMPT_COLLAPSE_LENGTH
  $: visiblePrompt =
    promptIsLong && !promptExpanded
      ? `${prompt.slice(0, PROMPT_COLLAPSE_LENGTH)}…`
      : prompt
</script>

<div
  class="max-w-md rounded-md bg-base-content/[0.04] px-3 py-2.5 flex flex-col gap-2"
>
  <div class="flex items-center gap-1.5 text-xs text-base-content/70">
    <span class="font-semibold text-base-content/90">Spawn sub-agent</span>
    {#if name}
      <span class="truncate">{name}</span>
    {/if}
    {#if agentType}
      <span
        class="shrink-0 rounded-full bg-base-content/[0.06] px-2 py-0.5 text-[10px]"
        >{agentType}</span
      >
    {/if}
  </div>
  {#if prompt}
    <div
      class="rounded bg-base-content/[0.04] px-2 py-1.5 text-xs text-base-content/70 whitespace-pre-wrap break-words"
    >
      {visiblePrompt}
      {#if promptIsLong}
        <button
          type="button"
          class="block mt-1 text-base-content/50 hover:text-base-content/80 underline"
          on:click={() => (promptExpanded = !promptExpanded)}
        >
          {promptExpanded ? "Show less" : "Show full briefing"}
        </button>
      {/if}
    </div>
  {/if}
  <p class="text-xs text-base-content/80 leading-relaxed">
    This sub-agent will work autonomously in the background — its tool calls run
    without asking. You'll only be asked once per conversation.
  </p>
  <div class="flex flex-row flex-wrap items-center justify-end gap-2">
    <button type="button" class="btn btn-ghost btn-sm" on:click={onSkip}>
      Skip
    </button>
    <button type="button" class="btn btn-primary btn-sm" on:click={onRun}>
      Allow sub-agents
    </button>
  </div>
</div>
