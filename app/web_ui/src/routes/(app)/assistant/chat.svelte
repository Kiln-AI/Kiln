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
  import {
    main_conversation_store,
    conversation_store,
  } from "$lib/chat/conversation_store"
  import ChatWelcome from "./chat_welcome.svelte"
  import ChatHistory from "./chat_history.svelte"
  import AutoModeConsentDialog from "./auto_mode_consent_dialog.svelte"
  import AutoModeStopDialog from "./auto_mode_stop_dialog.svelte"
  import ChatTranscript from "./chat_transcript.svelte"
  import SubagentTabs from "./subagent_tabs.svelte"
  import SubagentTranscript from "./subagent_transcript.svelte"
  import BrailleSpinner from "./braille_spinner.svelte"
  import ContextUsageGauge from "$lib/ui/context_usage_gauge.svelte"
  import { base_url } from "$lib/api_client"

  export let store: ChatSessionStore = chatSessionStore

  let costDisclaimer: ChatCostDisclaimer
  $: store.onConsentNeeded = () => costDisclaimer.prompt()
  let consentDialog: AutoModeConsentDialog
  let stopDialog: AutoModeStopDialog
  // The store asks here when the model requests auto mode; we just decide
  // accept/decline via the dialog. The store handles enable/decline + handoff.
  $: store.onAutoModeConsentNeeded = (payload) => consentDialog.prompt(payload)

  const autoModeOn = main_conversation_store.autoModeOn
  // Client-armed flag (Revision R2): auto mode turned on for a brand-new
  // conversation that has no server-side record yet. The indicator shows on
  // ("waiting for you") with no server run; the first message creates the run.
  const autoArmed = main_conversation_store.armed
  // The main conversation's session id (null until ensure/attach) — since
  // phase 5 the browser's ONLY conversation handle (functional spec §4).
  const mainSessionId = main_conversation_store.sessionId
  const autoModeWorking = main_conversation_store.working
  // Transient "reconnecting…" window while a re-attach (hard-refresh resync or
  // History restore) hydrates → attaches the live observer.
  const autoReconnecting = main_conversation_store.reconnecting
  // Transient "retrying N/M…" affordance while a transient upstream failure
  // (rate limit / 5xx / connection blip) is retried with backoff — carried by
  // the main conversation store for BOTH kinds (the session store's retry
  // field stays for compatibility but the observer owns it now).
  const autoRetry = main_conversation_store.retry
  // Observer connection state (FR5): while auto mode is on and the events
  // stream isn't open, the footer shows "reconnecting…" (bounded re-attach in
  // flight) or "connection lost" (attempts exhausted) instead of ever faking
  // the auto indicator off — the desktop-owned run is unaffected by observer
  // connection loss.
  const mainConnection = main_conversation_store.connection

  // Sub-agents (background child runs) of the current conversation, served by
  // the unified conversation store (children are keyed by session id and speak
  // the conversation-state vocabulary). The tab strip selects between the main
  // transcript and a child's read-only one; the composer routes to a running
  // child when its tab is selected.
  const subagentChildren = conversation_store.children
  const subagentSelectedId = conversation_store.selectedId
  const subagentTranscripts = conversation_store.transcripts
  const subagentRuntime = conversation_store.runtime

  // Assistant forensic debug logging (KILN_CHAT_DEBUG_LOG): when the desktop
  // flag is on, surface the conversation id — the join key for the desktop
  // and kiln_server debug logs — with click-to-copy. Follows the selected
  // tab so a sub-agent's id is just as reachable.
  let debugLogEnabled = false
  let debugIdCopied = false
  $: debugConversationId = selectedChild
    ? selectedChild.session_id
    : $mainSessionId ?? $store.sessionId
  async function fetchDebugStatus() {
    try {
      const res = await fetch(`${base_url}/api/chat/debug_status`)
      if (res.ok) {
        const parsed = (await res.json()) as { debug_log_enabled?: boolean }
        debugLogEnabled = Boolean(parsed?.debug_log_enabled)
      }
    } catch {
      // Debug affordance only — never surface an error for it.
    }
  }
  function copyDebugConversationId() {
    if (!debugConversationId) return
    void navigator.clipboard?.writeText(debugConversationId)
    debugIdCopied = true
    setTimeout(() => (debugIdCopied = false), 1200)
  }
  $: selectedChild = $subagentSelectedId
    ? $subagentChildren.find((c) => c.session_id === $subagentSelectedId) ??
      null
    : null
  $: selectedChildRunning = selectedChild?.state === "running"
  $: selectedChildMessages = selectedChild
    ? $subagentTranscripts.get(selectedChild.session_id) ?? []
    : []
  $: selectedChildRuntime = selectedChild
    ? $subagentRuntime.get(selectedChild.session_id) ?? null
    : null

  // The footer "Auto mode" toggle is shown whenever auto mode is off (the {:else}
  // branch), and is ALWAYS clickable (Revision R2) — including on a brand-new
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
      // Phase 5: the enable is keyed by the LIVE conversation's session id
      // (the old flow keyed it by a leaf trace id scanned off the messages —
      // the browser no longer holds trace ids, functional spec §4).
      const sessionId = get(mainSessionId)
      if (!sessionId) {
        // Brand-new conversation (Revision R2): no server record to flip, so
        // arm client-side. The indicator turns on ("waiting for you"); the
        // first message creates the run (enable seeded with that message).
        main_conversation_store.arm()
        return
      }
      // Existing conversation: enable FLIPS the same conversation record to
      // the auto policy (ARMED — no upstream POST; functional spec §4.1(2)).
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

    // Drop any pending queued message — stopping clears the queue. (detach()
    // below is silent, so onAutoModeOff won't fire to clear it for us.)
    store.clearQueued()

    // Hard stop: halt the agent completely — one stop for the one run (the
    // interactive stream and the auto burst are the same conversation task
    // since phase 4). The server cancels the run and publishes the off state;
    // the observer stays attached (the conversation continues interactively).
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
  // Phase 5: the server is summarizing earlier messages (compaction) for this
  // turn. Drives the same Thinking-style indicator with a "summarizing…" label.
  $: compacting = $store.compacting
  // A server-owned auto burst is running. Drives the SAME in-transcript loading
  // affordances (thinking dots / animated icon) as interactive streaming, while
  // leaving the input usable for inject-on-send.
  $: autoWorking = $store.autoWorking
  // Retry affordance from either source (auto burst or interactive stream).
  $: activeRetry = $autoRetry ?? $store.retry
  // The gauge follows the selected tab: a sub-agent tab shows THAT agent's
  // context usage (hydrated from its snapshot + live trace events), not the
  // main conversation's.
  $: contextUsage = selectedChild
    ? selectedChildRuntime?.contextUsage ?? null
    : $store.contextUsage
  $: upgradeNudgeVersion = $store.upgradeNudgeVersion
  $: versionRequired = $store.versionRequired
  // A message typed while a turn was in flight, held client-side and surfaced
  // above the composer with send-now / edit / cancel until it auto-sends.
  $: queuedMessage = $store.queuedMessage

  export let hasMessages = false
  $: messages = $store.messages
  $: hasMessages = messages.length > 0
  $: status = $store.status

  // Keep the sub-agent list in sync with the conversation the transcript
  // shows, keyed by the main conversation's SESSION id (phase 5 — the old
  // handle was a leaf trace id scanned off the messages, chain-resolved
  // server-side). Stable for the conversation's whole life, so the dedupe
  // inside syncForConversation makes the reactive call cheap; null (New
  // Chat / detached) clears the tab strip.
  $: void conversation_store.syncForConversation($mainSessionId)

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
  // burst, AND during a re-attach's brief "reconnecting…" window (Phase 9) so a
  // reattaching conversation doesn't look done/idle before liveness is known.
  // The composer stays usable throughout (see ``inputDisabled``) so a message
  // typed mid-turn is queued rather than blocked.
  $: transcriptLoading = isLoading || autoWorking || $autoReconnecting
  // The composer stays usable while a turn is in flight so a message typed mid-
  // turn is queued (held above the input, auto-sent when the turn yields) rather
  // than blocked. Disabled only for a too-old client (sending would just 426
  // again) or when a finished sub-agent's tab is selected (it can't receive
  // messages; return to Main to continue).
  $: inputDisabled =
    versionRequired || (selectedChild !== null && !selectedChildRunning)
  $: composerPlaceholder = selectedChild
    ? selectedChildRunning
      ? "Message this sub-agent…"
      : "This sub-agent has finished — select Main to continue the conversation."
    : "Type a message…"

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

  // Scroll the shared container to its end. Container-based (not the main
  // transcript's end anchor) so it works for whichever transcript is visible —
  // scrollIntoView on the hidden main anchor is a no-op while a sub-agent tab
  // is selected.
  function scrollToBottom(): void {
    const container = messagesContainer
    if (!container) return
    isAutoScrolling = true
    container.scrollTop = container.scrollHeight
    requestAnimationFrame(() => {
      isAutoScrolling = false
    })
  }

  // Switching tabs (main ↔ sub-agent) keeps the shared container's previous
  // scroll offset, which lands the newly shown transcript at the top — jump to
  // the bottom instead. Content that hydrates after the switch is carried the
  // rest of the way by the MutationObserver (userNearBottom is reset here).
  let prevSelectedTabId: string | null | undefined = undefined
  $: {
    const tabId = $subagentSelectedId
    if (prevSelectedTabId !== undefined && tabId !== prevSelectedTabId) {
      userNearBottom = true
      void tick().then(() => scrollToBottom())
    }
    prevSelectedTabId = tabId
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
    void fetchDebugStatus()

    // Watch the conversation-state firehose while the assistant page is active
    // so tabs reflect spawns/finishes even with no chat stream in flight.
    conversation_store.connect()

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
    conversation_store.disconnect()
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
    // The user-facing Stop kills the whole tree: cancelling the main run also
    // stops every running sub-agent (their loops have nothing left to report
    // to).
    store.stop({ cascade: true })
  }

  function stopSelectedChild() {
    const selected = selectedChild
    if (!selected) return
    void conversation_store.stop(selected.session_id)
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
    // Back to the main transcript; the loaded conversation's children sync
    // reactively from its session id once ensure() attaches.
    conversation_store.select(null)
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
    // A new conversation has no children yet; drop tabs/observers/selection.
    conversation_store.reset()
  }

  export function openHistory() {
    chatHistory.open()
  }

  async function handleSubmit(e?: Event) {
    if (e) e.preventDefault()
    const text = input.trim()
    // No isLoading guard: the store queues when a turn is in flight.
    if (!text) return
    // A sub-agent tab is selected: route the message to that child instead of
    // the main conversation. Terminal children can't receive messages (the
    // composer is disabled with a hint to return to Main).
    if (selectedChild) {
      if (!selectedChildRunning) return
      const result = await conversation_store.sendMessage(
        selectedChild.session_id,
        text,
      )
      if (!result.ok) return
      input = ""
      setTimeout(() => adjustTextareaHeight(), 0)
      return
    }
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
      {#if selectedChild}
        <!-- A sub-agent tab is selected: show its read-only transcript instead
           of the main one (which stays mounted, just hidden, so streaming
           state / observers are untouched while peeking at a child). -->
        <SubagentTranscript
          child={selectedChild}
          messages={selectedChildMessages}
          runtime={selectedChildRuntime}
        />
      {/if}
      <div
        class="flex flex-col gap-4 w-full min-h-full md:max-w-3xl mx-auto px-1"
        class:hidden={selectedChild !== null}
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
          <!-- Transient re-attach affordance (Phase 9): shown while a hard-refresh
             resync or History restore resolves → hydrates → attaches the live
             observer, so the transcript doesn't look done/idle before liveness
             is known. Clears the instant the events stream is established.
             Gated to the non-auto case: while auto mode is on, the footer's
             "reconnecting…" hint (FR5) owns the affordance — showing both
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

    <!-- The queued bubble belongs to the MAIN agent (the client queue only
       exists for the main conversation — sub-agent sends go straight to the
       child's server-side inbox), so it only renders on the Main tab. -->
    {#if queuedMessage && !selectedChild}
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

    <!-- Sub-agent tab strip (renders nothing when there are no children). -->
    <SubagentTabs />

    <form
      class="flex-none relative w-full md:max-w-3xl md:mx-auto px-1 pt-2"
      on:submit|preventDefault={handleSubmit}
    >
      <textarea
        bind:this={textareaRef}
        class="input input-bordered w-full min-h-[80px] max-h-[40vh] resize-none overflow-y-auto py-3 pr-12 text-sm"
        aria-label="Chat message"
        placeholder={composerPlaceholder}
        bind:value={input}
        disabled={inputDisabled}
        rows={3}
        on:input={() => adjustTextareaHeight()}
        on:keydown={handleTextareaKeydown}
      />
      {#if selectedChild && selectedChildRunning && !input.trim()}
        <!-- Kill this sub-agent (same stop the tab's × does, reachable from
           inside its transcript view). -->
        <button
          type="button"
          class="absolute right-3 bottom-6 btn btn-sm btn-circle btn-neutral"
          on:click={stopSelectedChild}
          aria-label="Stop this sub-agent"
        >
          <span class="size-4 block"><StopIcon /></span>
        </button>
      {:else if isLoading && !input.trim() && !selectedChild}
        <!-- Main-agent stop; hidden while a sub-agent tab is selected (the
           composer then addresses the child, not the main stream). -->
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
            <!-- FR5: connection hint, never a fake off — the run keeps going
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
        {#if debugLogEnabled && debugConversationId}
          <button
            type="button"
            class="btn btn-ghost btn-xs font-mono text-[10px] text-base-content/40 hover:text-base-content/70"
            on:click={copyDebugConversationId}
            title="Assistant debug logging is on — click to copy this conversation's id (the key for the desktop and server debug logs)."
            aria-label="Copy conversation id"
          >
            {debugIdCopied ? "copied" : debugConversationId}
          </button>
        {/if}
        {#if contextUsage}
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
