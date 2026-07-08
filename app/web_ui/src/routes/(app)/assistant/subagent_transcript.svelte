<script lang="ts">
  import type { SubAgentItem } from "$lib/chat/subagent_store"
  import type { ChatMessage, ChatMessagePart } from "$lib/chat/streaming_chat"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import ToolStatusLine from "./tool_status_line.svelte"
  import BrailleSpinner from "./braille_spinner.svelte"

  export let child: SubAgentItem
  export let messages: ChatMessage[] = []

  const STATUS_LABELS: Record<SubAgentItem["status"], string> = {
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    stopped: "Stopped",
    timeout: "Timed out",
  }

  function getPartText(part: ChatMessagePart): string {
    return "text" in part && typeof part.text === "string" ? part.text : ""
  }

  function isToolPart(part: ChatMessagePart): boolean {
    return typeof part.type === "string" && part.type.startsWith("tool-")
  }

  function getToolInputString(input: unknown, key: string): string {
    if (typeof input === "object" && input !== null && key in input) {
      const val = (input as Record<string, unknown>)[key]
      return typeof val === "string" ? val : ""
    }
    return ""
  }

  function toolVariant(
    part: ChatMessagePart,
    isLastMessage: boolean,
  ): "fetched" | "saved" | "fetching" | "saving" {
    const input = "input" in part ? part.input : undefined
    const method = getToolInputString(input, "method")
    const isGet = !method || method === "GET"
    const hasOutput = "output" in part && part.output !== undefined
    const complete = hasOutput || child.status !== "running" || !isLastMessage
    if (complete) return isGet ? "fetched" : "saved"
    return isGet ? "fetching" : "saving"
  }

  function toolDetail(part: ChatMessagePart): string {
    const input = "input" in part ? part.input : undefined
    const method = getToolInputString(input, "method")
    const urlPath = getToolInputString(input, "url_path")
    return method && urlPath ? `(${method} ${urlPath})` : ""
  }

  $: lastMessage = messages[messages.length - 1]
</script>

<div class="flex flex-col gap-4 w-full min-h-full md:max-w-3xl mx-auto px-1">
  <div
    class="sticky top-0 z-10 flex items-center gap-2 bg-base-100 py-2 text-xs text-base-content/60 border-b border-base-content/10"
  >
    <span class="font-medium text-sm text-base-content/80 truncate"
      >{child.name}</span
    >
    <span class="shrink-0 rounded-full bg-base-content/[0.06] px-2 py-0.5"
      >{child.agent_type}</span
    >
    <span
      class="shrink-0 ml-auto {child.status === 'running'
        ? 'text-primary'
        : child.status === 'completed'
          ? 'text-base-content/60'
          : 'text-error/80'}"
    >
      {#if child.status === "running"}
        <span class="inline-flex items-center gap-1.5">
          <BrailleSpinner />
          {STATUS_LABELS[child.status]}
        </span>
      {:else}
        {STATUS_LABELS[child.status]}
      {/if}
    </span>
  </div>
  {#each messages as message (message.id)}
    {#if message.role === "user"}
      <div
        class="leading-tight rounded-xl bg-base-content/[0.06] px-3 py-2.5 max-w-2xl ml-auto text-sm"
      >
        <div class="whitespace-pre-wrap">{message.content}</div>
      </div>
    {:else if message.role === "error"}
      <div
        class="rounded-lg bg-error/10 border border-error/30 px-3 py-2.5 text-error text-sm"
      >
        {message.content}
      </div>
    {:else if message.role === "assistant" && (message.parts?.length ?? 0) > 0}
      <div class="flex flex-col leading-tight">
        {#each message.parts ?? [] as part}
          {#if part.type === "text"}
            <ChatMarkdown text={getPartText(part)} />
          {:else if isToolPart(part)}
            <ToolStatusLine
              variant={toolVariant(part, message.id === lastMessage?.id)}
              detail={toolDetail(part)}
            />
          {/if}
        {/each}
      </div>
    {/if}
  {/each}
  {#if child.status === "running"}
    <div
      class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5"
      role="status"
    >
      <BrailleSpinner />
      <span>Working…</span>
    </div>
  {/if}
  <div class="shrink-0 min-h-[24px]" aria-hidden="true" />
</div>
