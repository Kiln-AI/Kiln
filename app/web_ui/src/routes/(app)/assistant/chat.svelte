<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte"
  import { get } from "svelte/store"
  import { fly } from "svelte/transition"
  import posthog from "posthog-js"
  import ChatCostDisclaimer from "./chat_cost_disclaimer.svelte"
  import type { ChatMessage, ChatMessagePart } from "$lib/chat/streaming_chat"
  import type { LoadedChatSessionDetail } from "$lib/chat/chat_history_apply"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import ArrowUpIcon from "$lib/ui/icons/arrow_up_icon.svelte"
  import StopIcon from "$lib/ui/icons/stop_icon.svelte"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import {
    chatSessionStore,
    type ChatSessionStore,
  } from "$lib/chat/chat_session_store"
  import { auto_run_store } from "$lib/chat/auto_run_store"
  import { traceIdForNextChatRequest } from "$lib/chat/streaming_chat"
  import ChatWelcome from "./chat_welcome.svelte"
  import ChatHistory from "./chat_history.svelte"
  import AutoModeConsentDialog from "./auto_mode_consent_dialog.svelte"
  import ToolApprovalBox from "./tool_approval_box.svelte"
  import ChatStatusSteps from "./chat_status_steps.svelte"
  import BrailleSpinner from "./braille_spinner.svelte"
  import ToolStatusLine from "./tool_status_line.svelte"
  import ContextUsageGauge from "$lib/ui/context_usage_gauge.svelte"

  export let store: ChatSessionStore = chatSessionStore

  let costDisclaimer: ChatCostDisclaimer
  $: store.onConsentNeeded = () => costDisclaimer.prompt()
  let consentDialog: AutoModeConsentDialog
  // The store asks here when the model requests auto mode; we just decide
  // accept/decline via the dialog. The store handles enable/decline + handoff.
  $: store.onAutoModeConsentNeeded = (payload) => consentDialog.prompt(payload)

  const autoModeOn = auto_run_store.autoModeOn
  // Client-armed flag (Revision R2): auto mode turned on for a brand-new
  // conversation that has no trace_id yet. The indicator shows on ("waiting for
  // you") with no server run; the first message creates the run.
  const autoArmed = auto_run_store.armed
  const autoModeWorking = auto_run_store.working
  // Transient "reconnecting…" window while a re-attach (hard-refresh resync or
  // History restore) resolves → hydrates → attaches the live observer (Phase 9).
  const autoReconnecting = auto_run_store.reconnecting
  // Transient "retrying N/M…" affordance while a transient upstream failure
  // (rate limit / 5xx / connection blip) is retried with backoff. Auto mode
  // surfaces it via auto_run_store; interactive chat via the session store. Only
  // one can be active at a time, so prefer whichever is set.
  const autoRetry = auto_run_store.retry

  // The footer "Auto mode" toggle is shown whenever auto mode is off (the {:else}
  // branch), and is ALWAYS clickable (Revision R2) — including on a brand-new
  // empty chat. It is disabled only while a consent prompt is already open (so we
  // never stack dialogs). On a conversation with a trace_id, enable arms a
  // server-owned run (IDLE); with no trace_id yet it arms client-side (no server
  // call) and the first message creates the run.
  let consentPending = false

  async function openManualAutoMode() {
    if (consentPending) return
    consentPending = true
    // Hold consentPending (the button's only disable guard) through the whole
    // flow — including the awaited requestEnable() — so a slow enable can't
    // re-enable the button and dispatch a duplicate enable.
    try {
      const accepted = await consentDialog.prompt(null)
      if (!accepted) return
      const traceId = traceIdForNextChatRequest(messages)
      if (!traceId) {
        // Brand-new conversation (Revision R2): no trace to key a server run, so
        // arm client-side. The indicator turns on ("waiting for you"); the first
        // message creates the run (enable seeded with that message, no trace_id).
        auto_run_store.arm()
        return
      }
      // Existing conversation: enable arms a server-owned run keyed by the trace
      // id (functional spec §4.1(2)). Surface enable failures (e.g. 429) instead
      // of silently swallowing them — the dialog has already closed.
      const result = await auto_run_store.requestEnable({ trace_id: traceId })
      if (!result.ok) {
        store.pushInlineError(
          `Couldn't start auto mode: ${result.error ?? "unknown error"}`,
        )
      }
    } finally {
      consentPending = false
    }
  }

  async function stopAutoMode() {
    // A client-armed (no-run) conversation just disarms locally; a real server
    // run is stopped via the registry. Always clear the armed flag so disable
    // before the first send returns the toggle to off (functional spec §4.1(2)).
    auto_run_store.disarm()
    await auto_run_store.stop()
  }

  let chatHistory: { open: () => void }
  let input = ""
  let messagesContainer: HTMLDivElement | null = null
  let messagesEndRef: HTMLDivElement | null = null
  let scrollObserver: MutationObserver | null = null
  let textareaRef: HTMLTextAreaElement | null = null

  $: toolApprovalWaiter = $store.toolApprovalWaiter
  $: toolApprovalPicks = $store.toolApprovalPicks
  $: showActivityIndicator = $store.showActivityIndicator
  // Phase 5: the server is summarizing earlier messages (compaction) for this
  // turn. Drives the same Thinking-style indicator with a "summarizing…" label.
  $: compacting = $store.compacting
  // A server-owned auto burst is running. Drives the SAME in-transcript loading
  // affordances (thinking dots / animated icon) as interactive streaming, while
  // leaving the input usable for inject-on-send.
  $: autoWorking = $store.autoWorking
  // Retry affordance from either source (auto burst or interactive stream).
  $: activeRetry = $autoRetry ?? $store.retry
  $: contextUsage = $store.contextUsage
  $: upgradeNudgeVersion = $store.upgradeNudgeVersion
  $: versionRequired = $store.versionRequired

  export let hasMessages = false
  $: messages = $store.messages
  $: hasMessages = messages.length > 0
  $: status = $store.status

  let expandedStepGroups: Record<string, boolean> = {}
  const MAX_VISIBLE_STEPS = 5

  function toggleStepGroupExpanded(key: string): void {
    suppressAutoScroll = true
    expandedStepGroups = {
      ...expandedStepGroups,
      [key]: !expandedStepGroups[key],
    }
    setTimeout(() => {
      suppressAutoScroll = false
    }, 50)
  }

  $: isLoading = status === "submitted" || status === "streaming"
  // The transcript's loading affordances (thinking dots, animated icon, active
  // tool lines) show for BOTH the interactive client stream and a live auto
  // burst, AND during a re-attach's brief "reconnecting…" window (Phase 9) so a
  // reattaching conversation doesn't look done/idle before liveness is known.
  // The input/send/Stop controls stay bound to ``isLoading`` only, so the
  // textarea remains usable for inject-on-send while auto mode works.
  $: transcriptLoading = isLoading || autoWorking || $autoReconnecting
  // Block input entirely when the client is too old: sending would just 426
  // again and the message would go nowhere.
  $: inputDisabled = isLoading || versionRequired

  let prevIsLoading = false
  $: {
    if (prevIsLoading && !isLoading) {
      tick().then(() => {
        textareaRef?.focus({ preventScroll: true })
      })
    }
    prevIsLoading = isLoading
  }

  $: lastMessage = messages[messages.length - 1]
  $: lastParts = lastMessage?.parts ?? []

  $: showStreamingCursor =
    transcriptLoading &&
    lastMessage?.role === "assistant" &&
    lastParts.length === 0

  function isMessageVisible(message: ChatMessage): boolean {
    if (message.role !== "assistant") return true
    if (transcriptLoading && message.id === lastMessage?.id) return true
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
    if (!(transcriptLoading && message.id === lastMessage?.id)) return false

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

  let suppressAutoScroll = false
  let userNearBottom = true
  let isAutoScrolling = false
  const SCROLL_THRESHOLD = 0.5

  function handleScroll() {
    if (isAutoScrolling || !messagesContainer) return
    const { scrollTop, scrollHeight, clientHeight } = messagesContainer
    if (scrollTop + clientHeight >= scrollHeight - SCROLL_THRESHOLD) {
      userNearBottom = true
    }
  }

  function handleWheel(e: WheelEvent) {
    if (e.deltaY < 0) {
      userNearBottom = false
    }
  }

  function handleTouchStart(e: TouchEvent) {
    lastTouchY = e.touches[0]?.clientY ?? 0
  }

  function handleTouchMove(e: TouchEvent) {
    const currentY = e.touches[0]?.clientY ?? 0
    if (currentY > lastTouchY) {
      userNearBottom = false
    }
    lastTouchY = currentY
  }

  let lastTouchY = 0

  onMount(() => {
    // Surface the upgrade banners up front, before any message is sent.
    void store.checkVersionPolicy()

    const container = messagesContainer
    const end = messagesEndRef
    if (container && end) {
      container.addEventListener("scroll", handleScroll, { passive: true })
      container.addEventListener("wheel", handleWheel, { passive: true })
      container.addEventListener("touchstart", handleTouchStart, {
        passive: true,
      })
      container.addEventListener("touchmove", handleTouchMove, {
        passive: true,
      })
      if (messages.length > 0) {
        end.scrollIntoView({ block: "end", behavior: "auto" })
      }
      let rafPending = false
      scrollObserver = new MutationObserver(() => {
        if (!suppressAutoScroll && userNearBottom && !rafPending) {
          rafPending = true
          requestAnimationFrame(() => {
            rafPending = false
            isAutoScrolling = true
            end.scrollIntoView({ block: "end", behavior: "auto" })
            requestAnimationFrame(() => {
              isAutoScrolling = false
            })
          })
        }
      })
      scrollObserver.observe(container, {
        childList: true,
        subtree: true,
        attributes: true,
        characterData: true,
      })
    }
    tick().then(() => {
      textareaRef?.focus({ preventScroll: true })
    })
    // Resync after a hard refresh: if the restored conversation has an active
    // server-owned auto run, hydrate from its current leaf and re-attach so the
    // indicator + live events come back (mirrors the History restore path).
    void store.resyncOnLoad()
  })

  onDestroy(() => {
    messagesContainer?.removeEventListener("scroll", handleScroll)
    messagesContainer?.removeEventListener("wheel", handleWheel)
    messagesContainer?.removeEventListener("touchstart", handleTouchStart)
    messagesContainer?.removeEventListener("touchmove", handleTouchMove)
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

  function applyToolApprovalRun(toolCallId: string): void {
    store.applyToolApprovalRun(toolCallId)
  }

  function applyToolApprovalSkip(toolCallId: string): void {
    store.applyToolApprovalSkip(toolCallId)
  }

  function retryLastRequest() {
    store.retryLastRequest()
  }

  function dismissUpgradeNudge() {
    store.dismissUpgradeNudge()
  }

  function stop() {
    store.stop()
  }

  function onChatHistoryApply(e: CustomEvent<LoadedChatSessionDetail>) {
    store.loadSession(
      e.detail.messages,
      e.detail.continuationTraceId,
      e.detail.contextUsage,
    )
    userNearBottom = true
    tick().then(() => {
      messagesEndRef?.scrollIntoView({ block: "end", behavior: "auto" })
      textareaRef?.focus({ preventScroll: true })
    })
  }

  export function newChat() {
    posthog.capture("chat_new_chat_clicked", {
      had_messages: get(store).messages.length > 0,
    })
    store.reset()
  }

  export function openHistory() {
    chatHistory.open()
  }

  async function handleSubmit(e?: Event) {
    if (e) e.preventDefault()
    const text = input.trim()
    if (!text || isLoading) return
    const sent = await store.sendMessage(text)
    if (!sent) return
    input = ""
    userNearBottom = true
    setTimeout(() => {
      adjustTextareaHeight()
      messagesEndRef?.scrollIntoView({ block: "end", behavior: "auto" })
    }, 0)
  }
</script>

<div class="flex flex-col flex-1 min-h-0">
  <div class="flex flex-col flex-1 min-h-0 overflow-hidden w-full">
    <ChatHistory bind:this={chatHistory} on:apply={onChatHistoryApply} />
    <div
      bind:this={messagesContainer}
      class="chat-messages-scroll flex-1 min-h-0 overflow-y-auto overflow-x-hidden"
      role="log"
      aria-live="polite"
    >
      <div
        class="flex flex-col gap-4 w-full min-h-full md:max-w-3xl mx-auto px-1"
      >
        {#if messages.length === 0 && !isLoading}
          <div class="flex-1 shrink-0"></div>
          <ChatWelcome
            on:select={async (e) => await store.sendMessage(e.detail)}
          />
          <div class="flex-[2] shrink-0"></div>
        {/if}
        {#each messages as message (message.id)}
          {#if isMessageVisible(message)}
            <div
              in:fly={{ y: 8, duration: 200 }}
              out:fly={{ y: -4, duration: 150 }}
              class={message.role === "user"
                ? "leading-tight rounded-xl bg-base-content/[0.06] px-3 py-2.5 max-w-2xl ml-auto text-sm"
                : message.role === "error"
                  ? "rounded-lg bg-error/10 border border-error/30 px-3 py-2.5 text-error text-sm"
                  : "flex flex-col gap-3"}
            >
              {#if message.role === "error"}
                <div class="flex items-center justify-between gap-3">
                  <span>{message.content}</span>
                  <button
                    type="button"
                    class="shrink-0 rounded-md bg-error/20 px-2 py-1 text-xs font-medium hover:bg-error/30 transition-colors"
                    on:click={retryLastRequest}
                    disabled={isLoading}
                  >
                    Retry
                  </button>
                </div>
              {:else}
                <div class="flex flex-col leading-tight">
                  {#if message.parts && message.parts.length > 0}
                    {@const segments = groupPartsForSimplifiedView(
                      message.parts ?? [],
                    )}
                    {#each segments as segment, segIdx}
                      {#if segment.kind === "text"}
                        {@const isFirstText =
                          segments.findIndex((s) => s.kind === "text") ===
                          segIdx}
                        {#if isFirstText}
                          {@const hasStepGroup = segments.some(
                            (s) => s.kind === "step-group",
                          )}
                          {#if !hasStepGroup}
                            <div
                              class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5"
                            >
                              <span class="inline-block w-3 text-center">✓</span
                              >
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
                          totalSteps > MAX_VISIBLE_STEPS &&
                          !isStepGroupExpanded}
                        {@const hiddenCount = totalSteps - MAX_VISIBLE_STEPS}
                        {@const visibleItems = shouldCompress
                          ? segment.items.slice(-MAX_VISIBLE_STEPS)
                          : segment.items}
                        <div class="flex items-start gap-3 min-w-0">
                          {#if groupLoading && !activeRetry}
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
                                on:click={() =>
                                  toggleStepGroupExpanded(stepGroupKey)}
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
                                <span class="inline-block w-3 text-center"
                                  >✓</span
                                >
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
                                {@const hasOutput =
                                  toolPart.output !== undefined}
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
                                  method && urlPath
                                    ? `(${method} ${urlPath})`
                                    : ""}
                                {@const isActiveMessage =
                                  transcriptLoading &&
                                  message.id === lastMessage?.id}
                                {@const effectivelyComplete =
                                  hasOutput || !isActiveMessage}
                                {#if pendingInlineApproval && toolApprovalPicks[tcId] === undefined}
                                  <div class="mt-2 text-sm">
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
                                      onRun={() => applyToolApprovalRun(tcId)}
                                      onSkip={() => applyToolApprovalSkip(tcId)}
                                    />
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
                                  (i) =>
                                    toolApprovalPicks[i.toolCallId] ===
                                    undefined,
                                )}
                              {#if !hasVisibleApproval}
                                <ChatStatusSteps
                                  parts={message.parts ?? []}
                                  isLoading={transcriptLoading &&
                                    message.id === lastMessage?.id}
                                  isLastMessage={message.id === lastMessage?.id}
                                  {showActivityIndicator}
                                  {compacting}
                                  retrying={activeRetry}
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
                            (i) =>
                              toolApprovalPicks[i.toolCallId] === undefined,
                          )}
                        {@const isActiveMessage =
                          transcriptLoading && message.id === lastMessage?.id}
                        {#if !hasVisibleApproval}
                          {#if isActiveMessage && showActivityIndicator}
                            <div class="flex items-start gap-3">
                              {#if !activeRetry}
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
                                  retrying={activeRetry}
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
                              retrying={activeRetry}
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
                      {#if !activeRetry}
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
                          retrying={activeRetry}
                        />
                      </div>
                    </div>
                  {:else if message.content}
                    <div class="whitespace-pre-wrap">{message.content}</div>
                  {/if}
                </div>
              {/if}
            </div>
          {/if}
        {/each}
        {#if (compacting || activeRetry) && lastMessage?.role !== "assistant"}
          <!-- Fallback compaction/retry indicator for when there is no active
             assistant bubble yet to host the in-place indicator above (so the
             summarizing / retrying copy still appears, and never alongside the
             bubble's Thinking — exactly one shows). When an empty assistant turn
             exists, the streaming-cursor branch above hosts the indicator. -->
          <div class="flex items-start gap-3" role="status">
            {#if !activeRetry}
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
                retrying={activeRetry}
              />
            </div>
          </div>
        {/if}
        {#if $autoReconnecting}
          <!-- Transient re-attach affordance (Phase 9): shown while a hard-refresh
             resync or History restore resolves → hydrates → attaches the live
             observer, so the transcript doesn't look done/idle before liveness
             is known. Clears the instant the events stream is established. -->
          <div
            class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5"
            role="status"
          >
            <BrailleSpinner />
            <span>Reconnecting…</span>
          </div>
        {/if}
        <div
          bind:this={messagesEndRef}
          class="shrink-0 min-w-[24px] min-h-[24px]"
          aria-hidden="true"
        />
      </div>
    </div>

    {#if versionRequired}
      <div class="flex-none w-full md:max-w-3xl md:mx-auto px-1 pt-2">
        <div class="rounded-lg border border-error/40 bg-error/5 px-3 py-2">
          <Warning
            warning_color="error"
            tight
            markdown
            trusted
            warning_message={"A newer version of Kiln is required to continue using chat. [Check for updates](/settings/check_for_update)"}
          />
        </div>
      </div>
    {:else if upgradeNudgeVersion}
      <div class="flex-none w-full md:max-w-3xl md:mx-auto px-1 pt-2">
        <div
          class="flex items-center gap-2 rounded-lg border border-warning/40 bg-warning/5 px-3 py-2"
        >
          <div class="flex-1 min-w-0">
            <Warning
              warning_color="warning"
              tight
              markdown
              trusted
              warning_message={`A newer version of Kiln (${upgradeNudgeVersion}) is available. [Check for updates](/settings/check_for_update)`}
            />
          </div>
          <button
            type="button"
            class="shrink-0 text-base-content/40 hover:text-base-content/70 transition-colors"
            on:click={dismissUpgradeNudge}
            aria-label="Dismiss upgrade notice"
          >
            <span class="size-4 block"><CloseIcon /></span>
          </button>
        </div>
      </div>
    {/if}

    <form
      class="flex-none relative w-full md:max-w-3xl md:mx-auto px-1 pt-2"
      on:submit|preventDefault={handleSubmit}
    >
      <textarea
        bind:this={textareaRef}
        class="input input-bordered w-full min-h-[80px] max-h-[40vh] resize-none overflow-y-auto py-3 pr-12 text-sm"
        aria-label="Chat message"
        placeholder="Type a message…"
        bind:value={input}
        disabled={inputDisabled}
        rows={3}
        on:input={() => adjustTextareaHeight()}
        on:keydown={handleTextareaKeydown}
      />
      {#if isLoading}
        <button
          type="button"
          class="absolute right-3 bottom-6 btn btn-sm btn-circle btn-neutral"
          on:click={stop}
          aria-label="Stop"
        >
          <span class="size-4 block"><StopIcon /></span>
        </button>
      {:else}
        <button
          type="submit"
          class="absolute right-3 bottom-6 btn btn-sm btn-circle btn-primary"
          disabled={!input.trim() || inputDisabled}
          aria-label="Send"
        >
          <span class="size-4 block"><ArrowUpIcon /></span>
        </button>
      {/if}
    </form>

    <div
      class="flex-none flex flex-wrap items-center gap-x-3 gap-y-1 pt-1.5 px-1 text-xs w-full md:max-w-3xl md:mx-auto"
    >
      {#if $autoModeOn || $autoArmed}
        <div class="flex items-center gap-2">
          <span
            class="inline-flex items-center gap-1.5 font-medium text-primary"
          >
            <span class:auto-pulse={$autoModeWorking} aria-hidden="true"
              >⏵⏵</span
            >
            <span>auto mode on</span>
            {#if !$autoModeWorking}
              <span class="font-normal text-primary/70">· waiting for you</span>
            {/if}
          </span>
          <button
            type="button"
            class="btn btn-ghost btn-xs text-error/80 hover:text-error hover:bg-error/10"
            on:click={stopAutoMode}
            title="Stop auto mode"
            aria-label="Stop auto mode"
          >
            ▸ Stop
          </button>
        </div>
      {:else}
        <button
          type="button"
          class="btn btn-ghost btn-xs text-base-content/50 hover:text-base-content/80 disabled:bg-transparent disabled:text-base-content/25"
          on:click={openManualAutoMode}
          disabled={consentPending}
          title="Let the assistant run steps automatically without asking for approval."
        >
          <span aria-hidden="true">⏵⏵</span>
          Auto mode
        </button>
      {/if}
      {#if contextUsage}
        <div class="ml-auto">
          <ContextUsageGauge usage={contextUsage} />
        </div>
      {/if}
    </div>
  </div>
</div>

<ChatCostDisclaimer bind:this={costDisclaimer} />
<AutoModeConsentDialog bind:this={consentDialog} />

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

  .auto-pulse {
    animation: auto-pulse 1.4s ease-in-out infinite;
  }

  @keyframes auto-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .auto-pulse {
      animation: none;
    }
  }
</style>
