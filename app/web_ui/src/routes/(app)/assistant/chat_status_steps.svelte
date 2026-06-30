<script lang="ts">
  import type { ChatMessagePart } from "$lib/chat/streaming_chat"
  import BrailleSpinner from "./braille_spinner.svelte"

  export let parts: ChatMessagePart[] = []
  export let isLoading: boolean = false
  export let isLastMessage: boolean = false
  export let showActivityIndicator: boolean = false
  /**
   * Phase 5: the server is summarizing earlier messages (compaction) for this
   * turn. When true, this same indicator shows the summarizing copy instead of
   * "Thinking", and takes precedence over the normal thinking gating.
   */
  export let compacting: boolean = false
  export let compactingMessage: string =
    "Summarizing earlier messages to free up context… this may take a little while."
  /**
   * A transient upstream failure is being retried (kiln-chat-retry):
   * ``{ attempt, max }`` while retrying, else null. Rendered here (error-styled)
   * in place of "Thinking"/compacting so exactly one busy indicator shows in the
   * row — no dangling spinner with no message.
   */
  export let retrying: { attempt: number; max: number } | null = null

  function isToolPart(p: ChatMessagePart): boolean {
    return typeof p.type === "string" && p.type.startsWith("tool-")
  }

  $: hasActiveTools = parts.some(
    (p) =>
      isToolPart(p) &&
      (!("output" in p) || (p as { output?: unknown }).output === undefined),
  )

  $: hasParts = parts.length > 0
  $: showThinking =
    isLoading &&
    isLastMessage &&
    !hasActiveTools &&
    (!hasParts || showActivityIndicator) &&
    !retrying
</script>

{#if retrying}
  <div
    class="flex items-center gap-1.5 text-sm text-error py-0.5"
    role="status"
  >
    <BrailleSpinner />
    <span>
      {#if retrying.max > 0}
        Temporary issue — retrying {retrying.attempt}/{retrying.max}…
      {:else}
        Temporary issue — retrying…
      {/if}
    </span>
  </div>
{:else if compacting}
  <div class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5">
    <BrailleSpinner />
    <span>
      {compactingMessage}<span class="inline-flex items-baseline gap-px"
        ><span class="thinking-dot" style="animation-delay: 0ms">.</span><span
          class="thinking-dot"
          style="animation-delay: 160ms">.</span
        ><span class="thinking-dot" style="animation-delay: 320ms">.</span
        ></span
      >
    </span>
  </div>
{:else if showThinking}
  <div class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5">
    <BrailleSpinner />
    <span>
      Thinking<span class="inline-flex items-baseline gap-px"
        ><span class="thinking-dot" style="animation-delay: 0ms">.</span><span
          class="thinking-dot"
          style="animation-delay: 160ms">.</span
        ><span class="thinking-dot" style="animation-delay: 320ms">.</span
        ></span
      >
    </span>
  </div>
{/if}
