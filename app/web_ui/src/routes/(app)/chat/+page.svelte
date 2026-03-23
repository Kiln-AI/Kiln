<script lang="ts">
  import { onMount, onDestroy } from "svelte"
  import { fly } from "svelte/transition"
  import AppPage from "../app_page.svelte"
  import {
    streamChat,
    chatGenerateId,
    traceIdForNextChatRequest,
    type ChatMessage,
    type ChatMessagePart,
  } from "$lib/chat/streaming_chat"
  import ChatMarkdown from "$lib/chat/ChatMarkdown.svelte"
  import ArrowUpIcon from "$lib/ui/icons/arrow_up_icon.svelte"
  import StopIcon from "$lib/ui/icons/stop_icon.svelte"
  import { base_url } from "$lib/api_client"

  const CHAT_API_URL = `${base_url}/api/chat`

  let messages: ChatMessage[] = []
  let input = ""
  let status: "ready" | "submitted" | "streaming" | "error" = "ready"
  let error: Error | null = null
  let abortController: AbortController | null = null
  let messagesContainer: HTMLDivElement | null = null
  let messagesEndRef: HTMLDivElement | null = null
  let scrollObserver: MutationObserver | null = null
  let textareaRef: HTMLTextAreaElement | null = null
  let collapsedPartKeys: Record<string, boolean> = {}
  let reasoningPartStartTimes: Record<string, number> = {}
  let reasoningPartEndTimes: Record<string, number> = {}
  let lastSeenLastPartKey: string | null = null

  $: isLoading = status === "submitted" || status === "streaming"

  $: lastMessage = messages[messages.length - 1]
  $: lastParts = lastMessage?.parts ?? []
  $: lastPartKey =
    lastParts.length > 0 && lastMessage
      ? partKey(
          lastMessage,
          lastParts[lastParts.length - 1],
          lastParts.length - 1,
        )
      : null

  $: if (lastPartKey !== lastSeenLastPartKey && lastSeenLastPartKey != null) {
    reasoningPartEndTimes = {
      ...reasoningPartEndTimes,
      [lastSeenLastPartKey]: Date.now(),
    }
  }
  $: lastSeenLastPartKey = lastPartKey

  $: if (
    status === "ready" &&
    lastPartKey != null &&
    !(lastPartKey in reasoningPartEndTimes)
  ) {
    reasoningPartEndTimes = {
      ...reasoningPartEndTimes,
      [lastPartKey]: Date.now(),
    }
  }

  $: {
    let updated = false
    const next = { ...reasoningPartStartTimes }
    for (const message of messages) {
      const parts = message.parts ?? []
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i]
        if (part.type === "reasoning") {
          const key = partKey(message, part, i)
          if (!(key in next)) {
            next[key] = Date.now()
            updated = true
          }
        }
      }
    }
    if (updated) reasoningPartStartTimes = next
  }

  function reasoningDurationSeconds(key: string): number | null {
    const start = reasoningPartStartTimes[key]
    const end = reasoningPartEndTimes[key]
    if (start == null) return null
    const endMs = end ?? Date.now()
    return Math.max(0, Math.round((endMs - start) / 1000))
  }

  function durationLabel(seconds: number): string {
    return seconds === 1 ? "1 second" : `${seconds} seconds`
  }

  $: showStreamingCursor =
    isLoading && lastMessage?.role === "assistant" && lastParts.length === 0

  function isReasoningStreaming(
    message: ChatMessage,
    partIndex: number,
    parts: ChatMessagePart[],
  ): boolean {
    const isLastMessage =
      messages.length > 0 && message.id === messages[messages.length - 1]?.id
    const isLastPart = partIndex === parts.length - 1
    return isLastMessage && status === "streaming" && isLastPart
  }

  function partKey(
    message: ChatMessage,
    part: ChatMessagePart,
    partIndex: number,
  ): string {
    if (part.type === "reasoning") return `${message.id}-reasoning-${partIndex}`
    if (
      typeof part.type === "string" &&
      part.type.startsWith("tool-") &&
      "toolCallId" in part
    ) {
      return `${message.id}-tool-${(part as { toolCallId: string }).toolCallId}`
    }
    return `${message.id}-part-${partIndex}`
  }

  function shouldAutoCollapse(
    message: ChatMessage,
    partIndex: number,
    parts: ChatMessagePart[],
  ): boolean {
    const isLastMessage =
      messages.length > 0 && message.id === messages[messages.length - 1]?.id
    const isLastPart = partIndex === parts.length - 1
    const isCurrentStreaming =
      isLastMessage && status === "streaming" && isLastPart
    return !isCurrentStreaming
  }

  function isPartCollapsed(
    state: Record<string, boolean>,
    message: ChatMessage,
    part: ChatMessagePart,
    partIndex: number,
    parts: ChatMessagePart[],
  ): boolean {
    const key = partKey(message, part, partIndex)
    if (key in state) return state[key]
    return shouldAutoCollapse(message, partIndex, parts)
  }

  function togglePartCollapsed(
    message: ChatMessage,
    part: ChatMessagePart,
    partIndex: number,
  ): void {
    const key = partKey(message, part, partIndex)
    const parts = message.parts ?? []
    const current = isPartCollapsed(
      collapsedPartKeys,
      message,
      part,
      partIndex,
      parts,
    )
    collapsedPartKeys = { ...collapsedPartKeys, [key]: !current }
  }

  function formatToolName(type: string): string {
    const name = type.startsWith("tool-") ? type.slice(5) : type
    return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  }

  function hasToolInput(part: ChatMessagePart): boolean {
    if (!("input" in part) || part.input === undefined) return false
    if (typeof part.input !== "object" || part.input === null) return true
    return Object.keys(part.input).length > 0
  }

  function formatToolInput(input: unknown): string {
    return typeof input === "string" ? input : JSON.stringify(input, null, 2)
  }

  function formatToolOutput(output: unknown): string {
    if (typeof output === "string") {
      try {
        const parsed = JSON.parse(output)
        return JSON.stringify(parsed, null, 2)
      } catch {
        return output
      }
    }
    return JSON.stringify(output, null, 2)
  }

  function getToolOutputError(part: ChatMessagePart): string {
    if (
      !("output" in part) ||
      typeof part.output !== "object" ||
      part.output === null
    )
      return "Error"
    return "error" in part.output &&
      typeof (part.output as { error?: string }).error === "string"
      ? (part.output as { error: string }).error
      : "Error"
  }

  onMount(() => {
    const container = messagesContainer
    const end = messagesEndRef
    if (container && end) {
      scrollObserver = new MutationObserver(() => {
        end.scrollIntoView({ block: "end", behavior: "auto" })
      })
      scrollObserver.observe(container, {
        childList: true,
        subtree: true,
        attributes: true,
        characterData: true,
      })
    }
  })

  onDestroy(() => {
    scrollObserver?.disconnect()
    scrollObserver = null
  })

  function handleTextareaKeydown(e: KeyboardEvent): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (!isLoading && input.trim()) handleSubmit()
    }
  }

  function adjustTextareaHeight(e?: Event): void {
    const el = (e?.currentTarget as HTMLTextAreaElement) ?? textareaRef
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight + 2, window.innerHeight * 0.4)}px`
  }

  function stop() {
    if (abortController) {
      abortController.abort()
    }
  }

  function updateLastAssistant(update: (draft: ChatMessage) => void) {
    const last = messages[messages.length - 1]
    if (last?.role === "assistant") {
      const draft = { ...last, parts: last.parts ? [...last.parts] : [] }
      update(draft)
      messages = [...messages.slice(0, -1), draft]
    }
  }

  function handleSubmit(e?: Event) {
    if (e) e.preventDefault()
    const text = input.trim()
    if (!text || isLoading) return
    error = null
    const userMessage: ChatMessage = {
      id: chatGenerateId(),
      role: "user",
      content: text,
    }
    const assistantMessage: ChatMessage = {
      id: chatGenerateId(),
      role: "assistant",
      parts: [],
    }
    messages = [...messages, userMessage, assistantMessage]
    input = ""
    status = "submitted"
    setTimeout(() => adjustTextareaHeight(), 0)
    abortController = new AbortController()

    const historyForRequest = messages.slice(0, -1)
    streamChat({
      apiUrl: CHAT_API_URL,
      messages: historyForRequest,
      traceId: traceIdForNextChatRequest(historyForRequest),
      onAssistantMessage: (update) => {
        status = "streaming"
        updateLastAssistant(update)
      },
      onChatTrace: (traceId) => {
        const last = messages[messages.length - 1]
        if (last?.role === "assistant") {
          messages = [...messages.slice(0, -1), { ...last, traceId }]
        }
      },
      onFinish: () => {
        status = "ready"
        abortController = null
      },
      onError: (err) => {
        status = "error"
        error = err
        abortController = null
      },
      signal: abortController.signal,
    })
  }
</script>

<AppPage
  title="Chat"
  subtitle="Streaming chat"
  limit_max_width={true}
  no_y_padding={true}
>
  <div
    class="flex flex-col h-[calc(100vh-14rem)] overflow-hidden w-full md:max-w-3xl mx-auto px-4"
  >
    {#if error}
      <div
        class="flex-none rounded-lg bg-error/10 border border-error/30 p-3 text-error text-sm"
      >
        {error?.message}
      </div>
    {/if}

    <div
      bind:this={messagesContainer}
      class="chat-messages-scroll flex-1 min-h-0 flex flex-col gap-4 overflow-y-auto overflow-x-hidden"
      role="log"
      aria-live="polite"
    >
      {#each messages as message (message.id)}
        <div
          in:fly={{ y: 8, duration: 200 }}
          out:fly={{ y: -4, duration: 150 }}
          class={message.role === "user"
            ? "rounded-xl bg-base-content/[0.06] px-3 py-2.5 max-w-2xl ml-auto"
            : "flex flex-col gap-3"}
        >
          <div class="flex flex-col gap-3">
            {#if message.parts && message.parts.length > 0}
              {#each message.parts as part, partIndex (partKey(message, part, partIndex))}
                {#if part.type === "text"}
                  <ChatMarkdown text={part.text ?? ""} />
                {:else if part.type === "reasoning"}
                  {@const collapsed = isPartCollapsed(
                    collapsedPartKeys,
                    message,
                    part,
                    partIndex,
                    message.parts ?? [],
                  )}
                  {@const key = partKey(message, part, partIndex)}
                  {@const streaming = isReasoningStreaming(
                    message,
                    partIndex,
                    message.parts ?? [],
                  )}
                  {@const duration = reasoningDurationSeconds(key)}
                  <div
                    class="mt-2 overflow-hidden text-sm text-base-content/60"
                  >
                    <button
                      type="button"
                      class="group/btn w-full flex items-center gap-1.5 py-1 text-left text-base-content/60 hover:text-base-content/80 transition-colors cursor-pointer"
                      on:click={() =>
                        togglePartCollapsed(message, part, partIndex)}
                    >
                      <span class="flex items-center gap-1.5 min-w-0">
                        {#if streaming}
                          <span class="inline-flex items-baseline gap-px">
                            Thinking
                            <span
                              class="thinking-dot"
                              style="animation-delay: 0ms">.</span
                            ><span
                              class="thinking-dot"
                              style="animation-delay: 160ms">.</span
                            ><span
                              class="thinking-dot"
                              style="animation-delay: 320ms">.</span
                            >
                          </span>
                        {:else}
                          <span
                            ><span class="font-semibold">Thought</span>
                            {#if duration != null}
                              for {durationLabel(duration)}
                            {:else}
                              …
                            {/if}</span
                          >
                        {/if}
                        {#if collapsed}
                          <span
                            class="shrink-0 text-base-content/40 transition-opacity opacity-0 group-hover/btn:opacity-100"
                            aria-hidden="true">▶</span
                          >
                        {:else}
                          <span
                            class="shrink-0 text-base-content/40"
                            aria-hidden="true">▼</span
                          >
                        {/if}
                      </span>
                    </button>
                    {#if !collapsed}
                      <div class="pt-1">
                        <ChatMarkdown text={part.reasoning ?? ""} />
                      </div>
                    {/if}
                  </div>
                {:else if typeof part.type === "string" && part.type.startsWith("tool-")}
                  {@const toolCollapsed = isPartCollapsed(
                    collapsedPartKeys,
                    message,
                    part,
                    partIndex,
                    message.parts ?? [],
                  )}
                  {@const hasOutput = part.output !== undefined}
                  {@const hasError =
                    hasOutput &&
                    typeof part.output === "object" &&
                    part.output !== null &&
                    "error" in part.output}
                  <div class="mt-2 overflow-hidden text-sm">
                    <button
                      type="button"
                      class="group/btn w-full flex items-center gap-1.5 py-1 text-left text-base-content/60 hover:text-base-content/80 transition-colors cursor-pointer"
                      on:click={() =>
                        togglePartCollapsed(message, part, partIndex)}
                    >
                      <span class="flex items-center gap-1.5">
                        {formatToolName(part.type)} was called
                        {#if toolCollapsed}
                          <span
                            class="shrink-0 text-base-content/40 transition-opacity opacity-0 group-hover/btn:opacity-100"
                            aria-hidden="true">▶</span
                          >
                        {:else}
                          <span
                            class="shrink-0 text-base-content/40"
                            aria-hidden="true">▼</span
                          >
                        {/if}
                      </span>
                    </button>
                    {#if !toolCollapsed}
                      <div
                        class="mt-2 overflow-hidden rounded-md {hasError
                          ? 'bg-error/5 text-error'
                          : 'bg-base-content/[0.04]'}"
                      >
                        <div class="px-3 py-2.5 flex flex-col gap-2.5">
                          <div>
                            <span
                              class="text-base-content/50 text-xs font-medium"
                              >Input</span
                            >
                            <div class="mt-0.5">
                              {#if hasToolInput(part)}
                                <pre
                                  class="text-xs overflow-x-auto rounded py-1.5 font-mono text-base-content/80">{formatToolInput(
                                    part.input,
                                  )}</pre>
                              {:else}
                                <span
                                  class="text-base-content/50 italic text-xs"
                                  >Calling…</span
                                >
                              {/if}
                            </div>
                          </div>
                          <div>
                            <span
                              class="text-base-content/50 text-xs font-medium"
                              >Output</span
                            >
                            <div class="mt-0.5">
                              {#if hasError}
                                <div class="text-xs">
                                  {getToolOutputError(part)}
                                </div>
                              {:else if hasOutput}
                                <pre
                                  class="text-xs overflow-x-auto rounded py-1.5 font-mono text-base-content/80">{formatToolOutput(
                                    part.output,
                                  )}</pre>
                              {:else}
                                <div
                                  class="flex items-center gap-2 text-base-content/50 italic text-xs"
                                >
                                  <span
                                    class="inline-block w-3 h-3 rounded-full border border-base-content/30 border-t-base-content/60 animate-spin"
                                  />
                                  <span>…</span>
                                </div>
                              {/if}
                            </div>
                          </div>
                        </div>
                      </div>
                    {/if}
                  </div>
                {/if}
              {/each}
            {:else if message.role === "assistant" && showStreamingCursor && message.id === lastMessage?.id}
              <div class="flex items-center py-0.5" aria-hidden="true">
                <span
                  class="inline-block w-2 h-2 rounded-full bg-base-content/60 animate-pulse"
                  style="animation-duration: 1.2s"
                />
              </div>
            {:else if message.content}
              <div class="whitespace-pre-wrap">{message.content}</div>
            {/if}
          </div>
        </div>
      {/each}
      <div
        bind:this={messagesEndRef}
        class="shrink-0 min-w-[24px] min-h-[24px]"
        aria-hidden="true"
      />
    </div>

    <form
      class="flex-none relative w-full pt-2 pb-3"
      on:submit|preventDefault={handleSubmit}
    >
      <textarea
        bind:this={textareaRef}
        class="input input-bordered w-full min-h-[80px] max-h-[40vh] resize-none overflow-y-auto py-3 pr-12"
        placeholder="Type a message…"
        bind:value={input}
        disabled={isLoading}
        rows={3}
        on:input={() => adjustTextareaHeight()}
        on:keydown={handleTextareaKeydown}
      />
      {#if isLoading}
        <button
          type="button"
          class="absolute right-3 bottom-6 flex size-8 items-center justify-center rounded-full bg-base-300 text-base-content hover:opacity-90 transition-opacity"
          on:click={stop}
          aria-label="Stop"
        >
          <span class="size-4 block"><StopIcon /></span>
        </button>
      {:else}
        <button
          type="submit"
          class="absolute right-3 bottom-6 flex size-8 items-center justify-center rounded-full bg-primary text-primary-content hover:opacity-90 disabled:bg-base-300 disabled:text-base-content/40 disabled:pointer-events-none transition-colors"
          disabled={!input.trim()}
          aria-label="Send"
        >
          <span class="size-4 block"><ArrowUpIcon /></span>
        </button>
      {/if}
    </form>
  </div>
</AppPage>

<style>
  .chat-messages-scroll::-webkit-scrollbar {
    width: 6px;
  }

  .chat-messages-scroll::-webkit-scrollbar-track {
    background: transparent;
  }

  .chat-messages-scroll::-webkit-scrollbar-thumb {
    background-color: oklch(var(--bc) / 0.2);
    border-radius: 3px;
  }

  .chat-messages-scroll::-webkit-scrollbar-thumb:hover {
    background-color: oklch(var(--bc) / 0.35);
  }

  .chat-messages-scroll {
    scrollbar-width: thin;
    scrollbar-color: oklch(var(--bc) / 0.2) transparent;
  }
</style>
