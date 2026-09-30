<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte"
  import { get } from "svelte/store"
  import { fly } from "svelte/transition"
  import posthog from "posthog-js"
  import ChatCostDisclaimer from "./chat_cost_disclaimer.svelte"
  import type { LoadedChatSessionDetail } from "$lib/chat/chat_history_apply"
  import ArrowUpIcon from "$lib/ui/icons/arrow_up_icon.svelte"
  import StopIcon from "$lib/ui/icons/stop_icon.svelte"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import TrashIcon from "$lib/ui/icons/trash_icon.svelte"
  import EditIcon from "$lib/ui/icons/edit_icon.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import {
    chatSessionStore,
    type ChatSessionStore,
  } from "$lib/chat/chat_session_store"
  import { main_conversation_store } from "$lib/chat/conversation_store"
  import ChatWelcome from "./chat_welcome.svelte"
  import ChatHistory from "./chat_history.svelte"
  import AutoModeConsentDialog from "./auto_mode_consent_dialog.svelte"
  import AutoModeStopDialog from "./auto_mode_stop_dialog.svelte"
  import ChatTranscript from "./chat_transcript.svelte"
  import BrailleSpinner from "./braille_spinner.svelte"
  import ContextUsageGauge from "$lib/ui/context_usage_gauge.svelte"
  import {
    chat_debug_log_enabled,
    load_chat_debug_status,
  } from "$lib/chat/chat_debug_status"
  import { dev_tools_enabled } from "$lib/utils/dev_tools"

  export let store: ChatSessionStore = chatSessionStore

  let costDisclaimer: ChatCostDisclaimer
  $: store.onConsentNeeded = () => costDisclaimer.prompt()
  let consentDialog: AutoModeConsentDialog
  let stopDialog: AutoModeStopDialog
  // The store asks here when the model requests auto mode; we just decide
  // accept/decline via the dialog. The store handles enable/decline + handoff.
  $: store.onAutoModeConsentNeeded = (payload) => consentDialog.prompt(payload)

  const autoModeOn = main_conversation_store.autoModeOn
  // Client-armed flag: auto mode turned on for a brand-new
  // conversation that has no server-side record yet. The indicator shows on
  // ("waiting for you") with no server run; the first message creates the run.
  const autoArmed = main_conversation_store.armed
  // The conversation's session id (null until ensure/attach): the browser's
  // ONLY conversation handle.
  const mainSessionId = main_conversation_store.sessionId
  const autoModeWorking = main_conversation_store.working
  // Transient "reconnecting…" window while a re-attach (hard-refresh resync or
  // History restore) hydrates → attaches the live observer.
  const autoReconnecting = main_conversation_store.reconnecting
  // Transient "retrying N/M…" affordance while a transient upstream failure
  // (rate limit / 5xx / connection blip) is retried with backoff, carried by
  // the main conversation store for BOTH kinds.
  const autoRetry = main_conversation_store.retry
  // Observer connection state: while auto mode is on and the events
  // stream isn't open, the footer shows "reconnecting…" (bounded re-attach in
  // flight) or "connection lost" (attempts exhausted) instead of ever faking
  // the auto indicator off — the desktop-owned run is unaffected by observer
  // connection loss.
  const mainConnection = main_conversation_store.connection

  // Assistant forensic debug logging (KILN_CHAT_DEBUG_LOG): when the desktop
  // flag is on, surface the conversation id — the join key for the desktop
  // and server debug logs — with click-to-copy.
  let debugIdCopied = false
  $: debugConversationId = $mainSessionId ?? $store.sessionId
  function copyDebugConversationId() {
    if (!debugConversationId) return
    void navigator.clipboard?.writeText(debugConversationId)
    debugIdCopied = true
    setTimeout(() => (debugIdCopied = false), 1200)
  }

  // The footer "Auto mode" toggle is shown whenever auto mode is off (the {:else}
  // branch), and is ALWAYS clickable, including on a brand-new
  // empty chat. It is disabled only while a consent prompt is already open (so we
  // never stack dialogs). On an observed conversation, enable arms a
  // server-owned run (IDLE); with no conversation yet it arms client-side (no
  // server call) and the first message creates the run.
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
      // The enable is keyed by the LIVE conversation's session id.
      const sessionId = get(mainSessionId)
      if (!sessionId) {
        // Brand-new conversation: no server record to flip, so
        // arm client-side. The indicator turns on ("waiting for you"); the
        // first message creates the run (enable seeded with that message).
        main_conversation_store.arm()
        return
      }
      // Existing conversation: enable FLIPS the same conversation record to
      // the auto policy (ARMED: no upstream POST).
      // Surface enable failures (e.g. 429) instead of silently swallowing
      // them — the dialog has already closed.
      const result = await main_conversation_store.requestEnable({
        kind: "auto",
        session_id: sessionId,
      })
      if (!result.ok) {
        store.pushInlineError(
          `Couldn't start auto mode: ${result.error ?? "unknown error"}`,
        )
      }
    } finally {
      consentPending = false
    }
  }

  async function stopAgent() {
    // Brand-new armed conversation: no server run exists yet, so nothing could
    // have been kicked off — just disarm without the explainer dialog.
    if (!get(autoModeOn)) {
      main_conversation_store.disarm()
      store.clearQueued()
      return
    }
    // Confirm + set expectations: the hard stop halts the agent immediately, but
    // jobs it already started (evals, optimization runs) are independent and keep
    // running. Bail if the user backs out.
    const confirmed = await stopDialog.prompt()
    if (!confirmed) return

    // Drop any pending queued message: stopping clears the queue.
    store.clearQueued()

    // Hard stop: halt the agent completely, one stop for the one run (the
    // interactive turn and the auto burst are the same conversation task).
    // The server cancels the run and publishes the off state; the observer
    // stays attached (the conversation continues interactively).
    // A client-armed (no-run) conversation has no server run; disarm() just
    // clears the local armed flag so the toggle returns to off.
    const stopping = main_conversation_store.stop()
    main_conversation_store.disarm()
    await stopping
  }

  let chatHistory: { open: () => void }
  let input = ""
  let messagesContainer: HTMLDivElement | null = null
  let scrollObserver: MutationObserver | null = null
  let textareaRef: HTMLTextAreaElement | null = null

  $: toolApprovalWaiter = $store.toolApprovalWaiter
  $: toolApprovalPicks = $store.toolApprovalPicks
  $: showActivityIndicator = $store.showActivityIndicator
  // The server is summarizing earlier messages (compaction) for this turn.
  // Drives the same Thinking-style indicator with a "summarizing…" label.
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
  // A message typed while a turn was in flight, held client-side and surfaced
  // above the composer with send-now / edit / cancel until it auto-sends.
  $: queuedMessage = $store.queuedMessage

  export let hasMessages = false
  $: messages = $store.messages
  $: hasMessages = messages.length > 0
  $: status = $store.status

  // Pause autoscroll around a step-group expand/collapse in the transcript
  // (the toggle mutates layout without new content arriving).
  function pauseAutoScrollForToggle(): void {
    suppressAutoScroll = true
    setTimeout(() => {
      suppressAutoScroll = false
    }, 50)
  }

  $: isLoading = status === "submitted" || status === "streaming"
  // The transcript's loading affordances (thinking dots, animated icon, active
  // tool lines) show for BOTH the interactive client stream and a live auto
  // burst, AND during a re-attach's brief "reconnecting…" window so a
  // reattaching conversation doesn't look done/idle before liveness is known.
  $: transcriptLoading = isLoading || autoWorking || $autoReconnecting
  // The composer stays usable while a turn is in flight so a message typed mid-
  // turn reaches the run (or is queued above the input) rather than blocked.
  // Disabled only for a too-old client (sending would just 426 again).
  $: inputDisabled = versionRequired

  let prevIsLoading = false
  $: {
    if (prevIsLoading && !isLoading) {
      tick().then(() => {
        textareaRef?.focus({ preventScroll: true })
      })
    }
    prevIsLoading = isLoading
  }

  let suppressAutoScroll = false
  let userNearBottom = true
  let isAutoScrolling = false
  const SCROLL_THRESHOLD = 0.5

  function scrollToBottom(): void {
    const container = messagesContainer
    if (!container) return
    isAutoScrolling = true
    container.scrollTop = container.scrollHeight
    requestAnimationFrame(() => {
      isAutoScrolling = false
    })
  }

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

    // Debug-log affordance: show the conversation id when the flag is on.
    // Dev-tools-only — without the flag the widget never renders, so skip
    // the status fetch entirely.
    if (dev_tools_enabled) {
      void load_chat_debug_status()
    }

    const container = messagesContainer
    if (container) {
      container.addEventListener("scroll", handleScroll, { passive: true })
      container.addEventListener("wheel", handleWheel, { passive: true })
      container.addEventListener("touchstart", handleTouchStart, {
        passive: true,
      })
      container.addEventListener("touchmove", handleTouchMove, {
        passive: true,
      })
      if (messages.length > 0) {
        scrollToBottom()
      }
      let rafPending = false
      scrollObserver = new MutationObserver(() => {
        if (!suppressAutoScroll && userNearBottom && !rafPending) {
          rafPending = true
          requestAnimationFrame(() => {
            rafPending = false
            scrollToBottom()
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
      // No isLoading guard: submitting mid-turn queues the message.
      if (input.trim()) handleSubmit()
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

  function sendQueuedNow() {
    store.sendQueuedNow()
  }

  function cancelQueued() {
    store.clearQueued()
  }

  // Pull the queued message back into the composer to edit it (merging with any
  // in-progress text), then clear the queue so re-sending doesn't double it up.
  function editQueued() {
    const queued = $store.queuedMessage
    if (!queued) return
    const draft = input.trim()
    input = draft ? `${queued}\n\n${draft}` : queued
    store.clearQueued()
    tick().then(() => {
      adjustTextareaHeight()
      textareaRef?.focus({ preventScroll: true })
    })
  }

  function onChatHistoryApply(e: CustomEvent<LoadedChatSessionDetail>) {
    store.loadSession(
      e.detail.messages,
      e.detail.sessionId,
      e.detail.contextUsage,
      { autoActive: e.detail.autoActive, rootId: e.detail.rootId },
    )
    userNearBottom = true
    tick().then(() => {
      scrollToBottom()
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
    // No isLoading guard: the store injects or queues when a turn is in
    // flight.
    if (!text) return
    const sent = await store.sendMessage(text)
    if (!sent) return
    input = ""
    userNearBottom = true
    setTimeout(() => {
      adjustTextareaHeight()
      scrollToBottom()
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
        <ChatTranscript
          {messages}
          loading={transcriptLoading}
          {showActivityIndicator}
          {compacting}
          retrying={activeRetry}
          {toolApprovalWaiter}
          {toolApprovalPicks}
          onToolApprovalRun={applyToolApprovalRun}
          onToolApprovalSkip={applyToolApprovalSkip}
          onRetryLastRequest={retryLastRequest}
          retryDisabled={isLoading}
          onStepGroupToggle={pauseAutoScrollForToggle}
        />
        {#if $autoReconnecting && !$autoModeOn}
          <!-- Transient re-attach affordance: shown while a hard-refresh
             resync or History restore resolves → hydrates → attaches the live
             observer, so the transcript doesn't look done/idle before liveness
             is known. Clears the instant the events stream is established.
             Gated to the non-auto case: while auto mode is on, the footer's
             "reconnecting…" hint owns the affordance — showing both
             would render two simultaneous indicators. -->
          <div
            class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5"
            role="status"
          >
            <BrailleSpinner />
            <span>Reconnecting…</span>
          </div>
        {/if}
        <div class="shrink-0 min-w-[24px] min-h-[24px]" aria-hidden="true" />
      </div>
    </div>

    {#if versionRequired}
      <div class="flex-none w-full md:max-w-3xl md:mx-auto px-1 pt-2">
        <div class="rounded-lg border border-error/40 bg-error/5 px-3 py-2">
          <Warning
            warning_color="error"
            inline={true}
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
              inline={true}
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

    {#if queuedMessage}
      <div class="flex-none w-full md:max-w-3xl md:mx-auto px-1 pt-2">
        <div
          class="rounded-xl border border-base-content/10 bg-base-200 py-2.5"
          in:fly={{ y: 8, duration: 150 }}
        >
          <div class="flex items-center justify-between gap-2 px-3">
            <div class="text-xs text-base-content/50">
              Queued · sends as soon as possible
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <button
                type="button"
                class="btn btn-ghost btn-xs btn-circle text-base-content/50 hover:text-base-content/80"
                on:click={editQueued}
                title="Edit"
                aria-label="Edit queued message"
              >
                <span class="size-4 block"><EditIcon /></span>
              </button>
              <button
                type="button"
                class="btn btn-ghost btn-xs btn-circle text-base-content/50 hover:text-error"
                on:click={cancelQueued}
                title="Discard"
                aria-label="Discard queued message"
              >
                <span class="size-4 block"><TrashIcon /></span>
              </button>
              <button
                type="button"
                class="btn btn-xs btn-circle btn-primary"
                on:click={sendQueuedNow}
                title="Send now"
                aria-label="Send queued message now"
              >
                <span class="size-4 block"><ArrowUpIcon /></span>
              </button>
            </div>
          </div>
          <div
            class="queued-message-scroll mt-1.5 max-h-32 overflow-y-auto px-3 text-sm whitespace-pre-wrap break-words"
          >
            {queuedMessage}
          </div>
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
      {#if isLoading && !input.trim()}
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
          </span>
          <button
            type="button"
            class="btn btn-ghost btn-xs text-error/80 hover:text-error hover:bg-error/10"
            on:click={stopAgent}
            title="Stop the agent"
            aria-label="Stop the agent"
          >
            ▸ Stop
          </button>
          {#if $autoModeOn && $mainConnection !== "open"}
            <!-- Connection hint, never a fake off — the run keeps going
               on the desktop; the real state reconciles on re-attach. -->
            {#if $autoReconnecting}
              <span
                class="flex items-center gap-1.5 text-base-content/50"
                role="status"
              >
                <BrailleSpinner />
                <span>reconnecting…</span>
              </span>
            {:else if $mainConnection === "closed"}
              <span class="text-warning" role="status">connection lost</span>
            {/if}
          {/if}
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
      <div class="ml-auto flex items-center gap-2">
        {#if dev_tools_enabled && $chat_debug_log_enabled && debugConversationId}
          <button
            type="button"
            class="btn btn-ghost btn-xs font-mono text-[10px] text-base-content/40 hover:text-base-content/70"
            on:click={copyDebugConversationId}
            title="Assistant debug logging is on. Click to copy this conversation's id, the key for the desktop and server debug logs."
            aria-label="Copy conversation id"
          >
            {debugIdCopied ? "copied" : debugConversationId}
          </button>
        {/if}
        {#if dev_tools_enabled && contextUsage}
          <ContextUsageGauge usage={contextUsage} />
        {/if}
      </div>
    </div>
  </div>
</div>

<ChatCostDisclaimer bind:this={costDisclaimer} />
<AutoModeConsentDialog bind:this={consentDialog} />
<AutoModeStopDialog bind:this={stopDialog} />

<style>
  .chat-messages-scroll::-webkit-scrollbar,
  .queued-message-scroll::-webkit-scrollbar {
    width: 6px;
  }

  .chat-messages-scroll::-webkit-scrollbar-track,
  .queued-message-scroll::-webkit-scrollbar-track {
    background: transparent;
  }

  .chat-messages-scroll::-webkit-scrollbar-thumb,
  .queued-message-scroll::-webkit-scrollbar-thumb {
    background-color: oklch(var(--bc) / 0.2);
    border-radius: 3px;
  }

  .chat-messages-scroll::-webkit-scrollbar-thumb:hover,
  .queued-message-scroll::-webkit-scrollbar-thumb:hover {
    background-color: oklch(var(--bc) / 0.35);
  }

  .chat-messages-scroll,
  .queued-message-scroll {
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
