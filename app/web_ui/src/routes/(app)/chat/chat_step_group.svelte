<script lang="ts">
  import type { ChatMessagePart } from "$lib/chat/streaming_chat"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import BrailleSpinner from "./braille_spinner.svelte"
  import ToolApprovalBox from "./tool_approval_box.svelte"
  import ChatStatusSteps from "./chat_status_steps.svelte"

  export let items: Array<{ part: ChatMessagePart; partIndex: number }>
  export let groupLoading: boolean
  export let message: {
    id: string
    parts?: ChatMessagePart[]
  }
  export let isLoading: boolean
  export let isLastMessage: boolean
  export let showActivityIndicator: boolean
  export let showChatStatusSteps: boolean
  export let collapsedPartKeys: Record<string, boolean>
  export let toolApprovalWaiter: {
    payload: {
      items: Array<{
        toolCallId: string
        approvalDescription?: string
        input?: unknown
      }>
    }
  } | null
  export let toolApprovalPicks: Record<string, boolean | undefined>
  export let onTogglePartCollapsed: (
    part: ChatMessagePart,
    partIndex: number,
  ) => void
  export let onApplyToolApprovalRun: (toolCallId: string) => void
  export let onApplyToolApprovalSkip: (toolCallId: string) => void

  export let isPartCollapsed: (
    state: Record<string, boolean>,
    part: ChatMessagePart,
    partIndex: number,
    parts: ChatMessagePart[],
  ) => boolean

  export let isReasoningStreaming: (partIndex: number) => boolean

  function partKey(part: ChatMessagePart, partIndex: number): string {
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

  function getToolCallId(part: ChatMessagePart): string {
    if ("toolCallId" in part && typeof part.toolCallId === "string") {
      return part.toolCallId
    }
    return ""
  }

  function getToolInputString(input: unknown, key: string): string {
    if (typeof input === "object" && input !== null && key in input) {
      const val = (input as Record<string, unknown>)[key]
      return typeof val === "string" ? val : ""
    }
    return ""
  }

  function getPartReasoning(part: ChatMessagePart): string {
    return "reasoning" in part && typeof part.reasoning === "string"
      ? part.reasoning
      : ""
  }

  type ToolPart = {
    type: `tool-${string}`
    toolCallId: string
    toolName?: string
    input?: unknown
    output?: unknown
  }

  function asToolPart(part: ChatMessagePart): ToolPart {
    return part as ToolPart
  }

  $: hasReasoningInGroup = items.some(
    (i) => i.part.type === "reasoning" && getPartReasoning(i.part).length > 0,
  )
  $: hasToolsInGroup = items.some(
    (i) => typeof i.part.type === "string" && i.part.type.startsWith("tool-"),
  )
  $: parts = message.parts ?? []
</script>

<div class="flex items-start gap-3">
  {#if groupLoading}
    <img
      src="/images/chat_icon_animated.svg"
      alt=""
      class="w-7 h-7 shrink-0 mt-0.5"
    />
  {/if}
  <div class="flex flex-col">
    {#if !hasReasoningInGroup && hasToolsInGroup}
      <div
        class="flex items-center gap-1.5 text-sm text-base-content/60 py-0.5"
      >
        <span class="inline-block w-3 text-center">✓</span>
        <span>Thought</span>
      </div>
    {/if}
    {#each items as item (partKey(item.part, item.partIndex))}
      {#if item.part.type === "reasoning"}
        {@const collapsed = isPartCollapsed(
          collapsedPartKeys,
          item.part,
          item.partIndex,
          parts,
        )}
        {@const streaming = isReasoningStreaming(item.partIndex)}
        {@const reasoningText = getPartReasoning(item.part)}
        {@const hasContent = reasoningText.length > 0}
        {#if hasContent || streaming}
          <div class="overflow-hidden text-sm text-base-content/60">
            <button
              type="button"
              class="group/btn w-full flex items-center gap-1.5 py-0.5 text-left text-base-content/60 hover:text-base-content/80 transition-colors cursor-pointer"
              on:click={() => onTogglePartCollapsed(item.part, item.partIndex)}
            >
              <span class="flex items-center gap-1.5 min-w-0">
                {#if streaming}
                  <span class="inline-flex items-baseline gap-px">
                    Thinking
                    <span class="thinking-dot" style="animation-delay: 0ms"
                      >.</span
                    ><span class="thinking-dot" style="animation-delay: 160ms"
                      >.</span
                    ><span class="thinking-dot" style="animation-delay: 320ms"
                      >.</span
                    >
                  </span>
                {:else}
                  <span>Thought</span>
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
                {/if}
              </span>
            </button>
            {#if !collapsed}
              <div class="pt-1">
                <ChatMarkdown text={reasoningText} />
              </div>
            {/if}
          </div>
        {/if}
      {:else if typeof item.part.type === "string" && item.part.type.startsWith("tool-")}
        {@const toolPart = asToolPart(item.part)}
        {@const tcId = getToolCallId(toolPart)}
        {@const approvalItem = toolApprovalWaiter?.payload.items.find(
          (i) => i.toolCallId === tcId,
        )}
        {@const pendingInlineApproval =
          toolApprovalWaiter !== null &&
          approvalItem !== undefined &&
          toolPart.output === undefined}
        {@const hasOutput = toolPart.output !== undefined}
        {@const method = getToolInputString(toolPart.input, "method")}
        {@const urlPath = getToolInputString(toolPart.input, "url_path")}
        {@const isGet = !method || method === "GET"}
        {@const detail = method && urlPath ? `(${method} ${urlPath})` : ""}
        {@const isActiveMessage = isLoading && isLastMessage}
        {@const effectivelyComplete = hasOutput || !isActiveMessage}
        {#if pendingInlineApproval && toolApprovalPicks[tcId] === undefined}
          <div class="mt-2 text-sm">
            <ToolApprovalBox
              description={approvalItem?.approvalDescription ?? ""}
              method={getToolInputString(approvalItem?.input, "method")}
              url={getToolInputString(approvalItem?.input, "url_path")}
              onRun={() => onApplyToolApprovalRun(tcId)}
              onSkip={() => onApplyToolApprovalSkip(tcId)}
            />
          </div>
        {:else}
          <div
            class="flex items-center gap-1.5 text-sm text-base-content/60 py-0.5"
          >
            {#if effectivelyComplete}
              <span class="inline-block w-3 text-center">✓</span>
              <span>
                {isGet ? "Fetched data" : "Saved data"}
                {#if detail}
                  <span class="text-base-content/35">{detail}</span>
                {/if}
              </span>
            {:else}
              <BrailleSpinner />
              <span>
                {isGet ? "Fetching data" : "Saving data"}<span
                  class="inline-flex items-baseline gap-px"
                  ><span class="thinking-dot" style="animation-delay: 0ms"
                    >.</span
                  ><span class="thinking-dot" style="animation-delay: 160ms"
                    >.</span
                  ><span class="thinking-dot" style="animation-delay: 320ms"
                    >.</span
                  ></span
                >
                {#if detail}
                  <span class="text-base-content/35">{detail}</span>
                {/if}
              </span>
            {/if}
          </div>
        {/if}
      {/if}
    {/each}
    {#if showChatStatusSteps}
      {@const hasVisibleApproval =
        toolApprovalWaiter !== null &&
        toolApprovalWaiter.payload.items.some(
          (i) => toolApprovalPicks[i.toolCallId] === undefined,
        )}
      {#if !hasVisibleApproval}
        <ChatStatusSteps
          {parts}
          isLoading={isLoading && isLastMessage}
          {isLastMessage}
          {showActivityIndicator}
        />
      {/if}
    {/if}
  </div>
</div>
