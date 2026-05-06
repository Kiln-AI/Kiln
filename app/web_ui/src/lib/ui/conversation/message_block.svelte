<script lang="ts">
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import type { TraceMessage } from "$lib/types"

  export let role: "user" | "assistant"
  export let content: string
  export let reasoning_content: string | null = null
  export let tool_messages: TraceMessage[] = []

  $: tool_messages_pretty = tool_messages.map((m) => {
    try {
      return JSON.stringify(m, null, 2)
    } catch {
      return String(m)
    }
  })
</script>

{#if role === "user"}
  <div
    class="self-end max-w-2xl rounded-xl bg-base-content/[0.06] px-4 py-2.5 text-sm leading-tight"
    data-testid="message-block"
    data-role="user"
  >
    <ChatMarkdown text={content} />
  </div>
{:else}
  <div
    class="flex flex-col gap-3 min-w-0 max-w-full"
    data-testid="message-block"
    data-role="assistant"
  >
    {#if reasoning_content}
      <details
        class="text-sm bg-base-200/40 rounded-md border border-base-200 max-w-full min-w-0"
        data-testid="message-block-reasoning"
      >
        <summary
          class="cursor-pointer px-3 py-2 text-base-content/70 select-none"
        >
          Reasoning
        </summary>
        <div class="px-3 pb-3 text-base-content/80 break-words">
          <ChatMarkdown text={reasoning_content} />
        </div>
      </details>
    {/if}

    {#if tool_messages.length > 0}
      <details
        class="text-sm bg-base-200/40 rounded-md border border-base-200 max-w-full min-w-0"
        data-testid="message-block-tools"
      >
        <summary
          class="cursor-pointer px-3 py-2 text-base-content/70 select-none"
        >
          Tool messages ({tool_messages.length})
        </summary>
        <div class="px-3 pb-3 flex flex-col gap-2 min-w-0">
          {#each tool_messages_pretty as pretty}
            <pre
              class="bg-base-300/40 rounded p-2 text-xs whitespace-pre-wrap break-words max-w-full">{pretty}</pre>
          {/each}
        </div>
      </details>
    {/if}

    {#if content}
      <ChatMarkdown text={content} />
    {/if}
  </div>
{/if}
