<script lang="ts">
  // Shared transcript renderer: the message loop extracted from chat.svelte so
  // the main view and the sub-agent observer view render with identical
  // fidelity (user bubbles, markdown text, step groups, tool status lines,
  // status steps, report chips). Main-agent-only concerns (welcome screen,
  // queued-message UI, banners, composer) stay in chat.svelte; approval boxes
  // render only when a waiter is passed (never in the read-only child view).
  import { fly } from "svelte/transition"
  import type { ChatMessage, ChatMessagePart } from "$lib/chat/streaming_chat"
  import type { ToolApprovalWaiter } from "$lib/chat/chat_session_store"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import ChatStatusSteps from "./chat_status_steps.svelte"
  import ToolStatusLine from "./tool_status_line.svelte"
  import ToolApprovalBox from "./tool_approval_box.svelte"
  import SubagentConsentBox from "./subagent_consent_box.svelte"
  import SubagentReportChip from "./subagent_report_chip.svelte"

  export let messages: ChatMessage[] = []
  /** A turn is live (interactive stream / auto burst / running sub-agent):
   * drives the thinking dots, animated icon and active tool spinners. */
  export let loading = false
  export let showActivityIndicator = false
  export let compacting = false
  /** "retrying N/M…" affordance ({ attempt, max }) or null. */
  export let retrying: { attempt: number; max: number } | null = null
  /**
   * Read-only observer view (sub-agent transcript): hides the error Retry
   * button. Approval boxes are off simply because no waiter is passed.
   */
  export let readOnly = false
  export let toolApprovalWaiter: ToolApprovalWaiter | null = null
  export let toolApprovalPicks: Record<string, boolean | undefined> = {}
  export let onToolApprovalRun: (toolCallId: string) => void = () => {}
  export let onToolApprovalSkip: (toolCallId: string) => void = () => {}
  export let onRetryLastRequest: () => void = () => {}
  export let retryDisabled = false
  /** Fired before a step-group expand/collapse so the host can pause its
   * autoscroll (the toggle mutates layout without new content). */
  export let onStepGroupToggle: () => void = () => {}

  let expandedStepGroups: Record<string, boolean> = {}
  const MAX_VISIBLE_STEPS = 5

  function toggleStepGroupExpanded(key: string): void {
    onStepGroupToggle()
    expandedStepGroups = {
      ...expandedStepGroups,
      [key]: !expandedStepGroups[key],
    }
  }

  $: lastMessage = messages[messages.length - 1]
  $: lastParts = lastMessage?.parts ?? []

  $: showStreamingCursor =
    loading && lastMessage?.role === "assistant" && lastParts.length === 0

  function isMessageVisible(message: ChatMessage): boolean {
    if (message.role !== "assistant") return true
    if (loading && message.id === lastMessage?.id) return true
    const parts = message.parts ?? []
    if (parts.length === 0 && !message.content) return false
    return true
  }

  function partKey(
    message: ChatMessage,
    part: ChatMessagePart,
    partIndex: number,
  ): string {
    if (
      typeof part.type === "string" &&
      part.type.startsWith("tool-") &&
      "toolCallId" in part
    ) {
      return `${message.id}-tool-${(part as { toolCallId: string }).toolCallId}`
    }
    return `${message.id}-part-${partIndex}`
  }

  type RenderSegment =
    | { kind: "text"; part: ChatMessagePart; partIndex: number }
    | {
        kind: "step-group"
        items: Array<{ part: ChatMessagePart; partIndex: number }>
      }

  function groupPartsForSimplifiedView(
    parts: ChatMessagePart[],
  ): RenderSegment[] {
    const segments: RenderSegment[] = []
    let currentGroup: Array<{ part: ChatMessagePart; partIndex: number }> = []

    for (let i = 0; i < parts.length; i++) {
      if (parts[i].type === "text") {
        if (currentGroup.length > 0) {
          segments.push({ kind: "step-group", items: currentGroup })
          currentGroup = []
        }
        segments.push({ kind: "text", part: parts[i], partIndex: i })
      } else {
        currentGroup.push({ part: parts[i], partIndex: i })
      }
    }
    if (currentGroup.length > 0) {
      segments.push({ kind: "step-group", items: currentGroup })
    }
    return segments
  }

  function isStepGroupLoading(
    message: ChatMessage,
    groupSegment: RenderSegment & { kind: "step-group" },
    allSegments: RenderSegment[],
  ): boolean {
    if (!(loading && message.id === lastMessage?.id)) return false

    const groupIdx = allSegments.indexOf(groupSegment)
    const hasTextAfter = allSegments
      .slice(groupIdx + 1)
      .some((s) => s.kind === "text")
    if (hasTextAfter) return false

    const toolItems = groupSegment.items.filter(
      (i) => typeof i.part.type === "string" && i.part.type.startsWith("tool-"),
    )
    const allToolsComplete =
      toolItems.length > 0 &&
      toolItems.every(
        (i) =>
          "output" in i.part &&
          (i.part as { output?: unknown }).output !== undefined,
      )
    if (allToolsComplete && !showActivityIndicator) return false

    return true
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

  function getPartText(part: ChatMessagePart): string {
    return "text" in part && typeof part.text === "string" ? part.text : ""
  }
</script>

{#each messages as message (message.id)}
  {#if isMessageVisible(message)}
    <div
      in:fly={{ y: 8, duration: 200 }}
      out:fly={{ y: -4, duration: 150 }}
      class={message.role === "user"
        ? message.subagentReport
          ? ""
          : "leading-tight rounded-xl bg-base-content/[0.06] px-3 py-2.5 max-w-2xl ml-auto text-sm break-words"
        : message.role === "error"
          ? "rounded-lg bg-error/10 border border-error/30 px-3 py-2.5 text-error text-sm break-words"
          : "flex flex-col gap-3"}
    >
      {#if message.role === "error"}
        <div class="flex items-center justify-between gap-3">
          <span>{message.content}</span>
          {#if !readOnly}
            <button
              type="button"
              class="shrink-0 rounded-md bg-error/20 px-2 py-1 text-xs font-medium hover:bg-error/30 transition-colors"
              on:click={onRetryLastRequest}
              disabled={retryDisabled}
            >
              Retry
            </button>
          {/if}
        </div>
      {:else}
        <div class="flex flex-col leading-tight">
          {#if message.parts && message.parts.length > 0}
            {@const segments = groupPartsForSimplifiedView(message.parts ?? [])}
            {#each segments as segment, segIdx}
              {#if segment.kind === "text"}
                {@const isFirstText =
                  segments.findIndex((s) => s.kind === "text") === segIdx}
                {#if isFirstText}
                  {@const hasStepGroup = segments.some(
                    (s) => s.kind === "step-group",
                  )}
                  {#if !hasStepGroup}
                    <div
                      class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5"
                    >
                      <span class="inline-block w-3 text-center">✓</span>
                      <span>Thought</span>
                    </div>
                  {/if}
                {/if}
                <ChatMarkdown text={getPartText(segment.part)} />
              {:else}
                {@const groupLoading = isStepGroupLoading(
                  message,
                  segment,
                  segments,
                )}
                {@const hasToolsInGroup = segment.items.some(
                  (i) =>
                    typeof i.part.type === "string" &&
                    i.part.type.startsWith("tool-"),
                )}
                {@const stepGroupKey = `${message.id}-sg-${segIdx}`}
                {@const isStepGroupExpanded =
                  expandedStepGroups[stepGroupKey] === true}
                {@const totalSteps = segment.items.length}
                {@const shouldCompress =
                  totalSteps > MAX_VISIBLE_STEPS && !isStepGroupExpanded}
                {@const hiddenCount = totalSteps - MAX_VISIBLE_STEPS}
                {@const visibleItems = shouldCompress
                  ? segment.items.slice(-MAX_VISIBLE_STEPS)
                  : segment.items}
                <div class="flex items-start gap-3 min-w-0">
                  {#if groupLoading && !retrying}
                    <img
                      src="/images/chat_icon_animated.svg"
                      alt=""
                      class="w-9 h-9 shrink-0 -mt-1.5"
                    />
                  {/if}
                  <div class="flex flex-col min-w-0 flex-1">
                    {#if totalSteps > MAX_VISIBLE_STEPS}
                      <button
                        type="button"
                        class="flex items-center gap-1.5 text-sm text-base-content/40 hover:text-base-content/60 transition-colors cursor-pointer py-0.5"
                        on:click={() => toggleStepGroupExpanded(stepGroupKey)}
                      >
                        {#if isStepGroupExpanded}
                          <span>{totalSteps} steps ▼</span>
                        {:else}
                          <span>… {hiddenCount} more steps ▶</span>
                        {/if}
                      </button>
                    {/if}
                    {#if !shouldCompress && hasToolsInGroup}
                      <div
                        class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5"
                      >
                        <span class="inline-block w-3 text-center">✓</span>
                        <span>Thought</span>
                      </div>
                    {/if}
                    {#each visibleItems as item (partKey(message, item.part, item.partIndex))}
                      {#if typeof item.part.type === "string" && item.part.type.startsWith("tool-")}
                        {@const toolPart = asToolPart(item.part)}
                        {@const tcId = getToolCallId(toolPart)}
                        {@const approvalItem =
                          toolApprovalWaiter?.payload.items.find(
                            (i) => i.toolCallId === tcId,
                          )}
                        {@const pendingInlineApproval =
                          toolApprovalWaiter !== null &&
                          approvalItem !== undefined &&
                          toolPart.output === undefined}
                        {@const hasOutput = toolPart.output !== undefined}
                        {@const method = getToolInputString(
                          toolPart.input,
                          "method",
                        )}
                        {@const urlPath = getToolInputString(
                          toolPart.input,
                          "url_path",
                        )}
                        {@const isGet = !method || method === "GET"}
                        {@const detail =
                          method && urlPath ? `(${method} ${urlPath})` : ""}
                        {@const isActiveMessage =
                          loading && message.id === lastMessage?.id}
                        {@const effectivelyComplete =
                          hasOutput || !isActiveMessage}
                        {#if pendingInlineApproval && toolApprovalPicks[tcId] === undefined}
                          <div class="mt-2 text-sm">
                            {#if approvalItem?.toolName === "spawn_subagent"}
                              <!-- First spawn in a conversation: richer
                                 consent copy (later spawns auto-run). -->
                              <SubagentConsentBox
                                name={getToolInputString(
                                  approvalItem?.input,
                                  "name",
                                )}
                                agentType={getToolInputString(
                                  approvalItem?.input,
                                  "agent_type",
                                )}
                                prompt={getToolInputString(
                                  approvalItem?.input,
                                  "prompt",
                                )}
                                onRun={() => onToolApprovalRun(tcId)}
                                onSkip={() => onToolApprovalSkip(tcId)}
                              />
                            {:else}
                              <ToolApprovalBox
                                description={approvalItem?.approvalDescription ??
                                  ""}
                                method={getToolInputString(
                                  approvalItem?.input,
                                  "method",
                                )}
                                url={getToolInputString(
                                  approvalItem?.input,
                                  "url_path",
                                )}
                                onRun={() => onToolApprovalRun(tcId)}
                                onSkip={() => onToolApprovalSkip(tcId)}
                              />
                            {/if}
                          </div>
                        {:else}
                          <ToolStatusLine
                            variant={effectivelyComplete
                              ? isGet
                                ? "fetched"
                                : "saved"
                              : isGet
                                ? "fetching"
                                : "saving"}
                            {detail}
                          />
                        {/if}
                      {/if}
                    {/each}
                    {#if segIdx === segments.length - 1 && message.role === "assistant" && message.id === lastMessage?.id}
                      {@const hasVisibleApproval =
                        toolApprovalWaiter !== null &&
                        toolApprovalWaiter.payload.items.some(
                          (i) => toolApprovalPicks[i.toolCallId] === undefined,
                        )}
                      {#if !hasVisibleApproval}
                        <ChatStatusSteps
                          parts={message.parts ?? []}
                          isLoading={loading && message.id === lastMessage?.id}
                          isLastMessage={message.id === lastMessage?.id}
                          {showActivityIndicator}
                          {compacting}
                          {retrying}
                        />
                      {/if}
                    {/if}
                  </div>
                </div>
              {/if}
            {/each}
            {#if message.role === "assistant"}
              {@const segments = groupPartsForSimplifiedView(
                message.parts ?? [],
              )}
              {@const lastSegIsText =
                segments.length > 0 &&
                segments[segments.length - 1].kind === "text"}
              {#if lastSegIsText && message.id === lastMessage?.id}
                {@const hasVisibleApproval =
                  toolApprovalWaiter !== null &&
                  toolApprovalWaiter.payload.items.some(
                    (i) => toolApprovalPicks[i.toolCallId] === undefined,
                  )}
                {@const isActiveMessage =
                  loading && message.id === lastMessage?.id}
                {#if !hasVisibleApproval}
                  {#if isActiveMessage && showActivityIndicator}
                    <div class="flex items-start gap-3">
                      {#if !retrying}
                        <img
                          src="/images/chat_icon_animated.svg"
                          alt=""
                          class="w-9 h-9 shrink-0 -mt-1.5"
                        />
                      {/if}
                      <div class="flex flex-col">
                        <ChatStatusSteps
                          parts={message.parts ?? []}
                          isLoading={true}
                          isLastMessage={true}
                          {showActivityIndicator}
                          {compacting}
                          {retrying}
                        />
                      </div>
                    </div>
                  {:else}
                    <ChatStatusSteps
                      parts={message.parts ?? []}
                      isLoading={isActiveMessage}
                      isLastMessage={message.id === lastMessage?.id}
                      {showActivityIndicator}
                      {compacting}
                      {retrying}
                    />
                  {/if}
                {/if}
              {/if}
            {/if}
          {:else if message.role === "assistant" && showStreamingCursor && message.id === lastMessage?.id}
            <!-- The single pending indicator for the active assistant
               turn. While ``compacting`` it swaps its label in place to
               the summarizing copy (instead of a separate row); when
               compaction finishes it reverts to Thinking. -->
            <div class="flex items-start gap-3">
              {#if !retrying}
                <img
                  src="/images/chat_icon_animated.svg"
                  alt=""
                  class="w-9 h-9 shrink-0 -mt-1.5"
                />
              {/if}
              <div class="flex flex-col">
                <ChatStatusSteps
                  parts={[]}
                  isLoading={true}
                  isLastMessage={true}
                  {showActivityIndicator}
                  {compacting}
                  {retrying}
                />
              </div>
            </div>
          {:else if message.subagentReport}
            <!-- Sub-agent completion report injected as a user-role
               message: render a collapsed chip instead of a bubble. -->
            <SubagentReportChip
              report={message.subagentReport}
              body={message.content ?? ""}
            />
          {:else if message.content}
            <div class="whitespace-pre-wrap break-words">{message.content}</div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
{/each}
{#if (compacting || retrying) && lastMessage?.role !== "assistant"}
  <!-- Fallback compaction/retry indicator for when there is no active
     assistant bubble yet to host the in-place indicator above (so the
     summarizing / retrying copy still appears, and never alongside the
     bubble's Thinking — exactly one shows). When an empty assistant turn
     exists, the streaming-cursor branch above hosts the indicator. -->
  <div class="flex items-start gap-3" role="status">
    {#if !retrying}
      <img
        src="/images/chat_icon_animated.svg"
        alt=""
        class="w-9 h-9 shrink-0 -mt-1.5"
      />
    {/if}
    <div class="flex flex-col">
      <ChatStatusSteps
        parts={[]}
        isLoading={true}
        isLastMessage={true}
        {compacting}
        {retrying}
      />
    </div>
  </div>
{/if}
