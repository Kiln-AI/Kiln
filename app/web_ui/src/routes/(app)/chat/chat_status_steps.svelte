<script lang="ts">
  import type { ChatMessagePart } from "$lib/chat/streaming_chat"
  import BrailleSpinner from "./braille_spinner.svelte"

  export let parts: ChatMessagePart[] = []
  export let isLoading: boolean = false
  export let isLastMessage: boolean = false
  export let showActivityIndicator: boolean = false

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
    (!hasParts || showActivityIndicator)
</script>

{#if showThinking}
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
