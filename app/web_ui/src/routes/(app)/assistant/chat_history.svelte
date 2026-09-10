<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import posthog from "posthog-js"
  import { client } from "$lib/api_client"
  import { hydrateSessionFromSnapshot } from "$lib/chat/session_messages"
  import type { LoadedChatSessionDetail } from "$lib/chat/chat_history_apply"
  import {
    nestSessionRows,
    splitSessionNodes,
    visibleSessionRows,
    type SessionListItem,
  } from "$lib/chat/session_grouping"
  import { dev_tools_enabled } from "$lib/utils/dev_tools"
  import { main_conversation_store } from "$lib/chat/conversation_store"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"
  import Dialog from "$lib/ui/dialog.svelte"
  import ChatIcon from "$lib/ui/icons/chat_icon.svelte"
  import ChatHistoryRow from "./chat_history_row.svelte"

  const dispatch = createEventDispatcher<{
    apply: LoadedChatSessionDetail
  }>()

  let historyDialog: Dialog | null = null
  let sessionsLoading = false
  let sessionsError: KilnError | null = null
  let sessionRows: SessionListItem[] = []
  let sessionDetailLoading: string | null = null
  let deletingSessionId: string | null = null

  // Sub-agent sessions nest under their parent conversation's row; a child
  // whose parent isn't visible renders as a normal top-level row. They are a
  // developer affordance: hidden entirely unless dev tools are enabled.
  $: visibleRows = visibleSessionRows(sessionRows, dev_tools_enabled)
  $: ({ active: activeNodes, recent: recentNodes } = splitSessionNodes(
    nestSessionRows(visibleRows),
  ))

  async function loadSessionList() {
    sessionsLoading = true
    sessionsError = null
    sessionRows = []
    try {
      const { data, error } = await client.GET("/api/chat/sessions")
      if (error) {
        sessionsError = createKilnError(error)
        return
      }
      sessionRows = data ?? []
    } catch (e) {
      sessionsError = createKilnError(e)
    } finally {
      sessionsLoading = false
    }
  }

  export function open() {
    if (!historyDialog) return
    historyDialog.show()
    posthog.capture("chat_history_opened")
    void loadSessionList()
  }

  function resetAfterClose() {
    sessionsError = null
  }

  function close() {
    historyDialog?.close()
  }

  async function selectSession(row: SessionListItem) {
    // Phase 5: row.id is an opaque conversation KEY (live session id /
    // upstream root id / legacy leaf — never a trace id the browser
    // interprets); the desktop resolves it to the current leaf for the
    // hydration GET and again on the ensure/adopt in the apply handler.
    const sessionId = row.id
    sessionDetailLoading = sessionId
    sessionsError = null
    try {
      const { data: snapshot, error } = await client.GET(
        "/api/chat/sessions/{session_id}",
        {
          params: { path: { session_id: sessionId } },
        },
      )
      if (error || !snapshot) {
        sessionsError = createKilnError(error)
        return
      }
      const { messages, rootId, contextUsage } =
        hydrateSessionFromSnapshot(snapshot)
      dispatch("apply", {
        messages,
        sessionId,
        // The durable recovery key: the row's root_id (present for every
        // non-legacy session) with the snapshot's copy as fallback.
        rootId: row.root_id ?? rootId,
        contextUsage,
        autoActive: !!row.auto_active,
      })
      posthog.capture("chat_history_session_loaded", {
        message_count: messages.length,
        auto_active: !!row.auto_active,
      })
      // The apply handler (chat.svelte → chatSessionStore.loadSession)
      // re-attaches the conversation's observer for EVERY kind since phase 4
      // (create-or-adopt by trace + attach: the replayed in-flight turn and
      // any parked approval converge on their own). For a live AUTO
      // conversation, additionally show the transient "reconnecting…"
      // affordance during the hydrate→attach window (old behavior — attach
      // clears it once the stream is established, and the on-subscribe
      // conversation-state marker restores the working/on indicators).
      if (row.auto_active) {
        main_conversation_store.beginReconnect()
      }
      close()
    } catch (e) {
      sessionsError = createKilnError(e)
    } finally {
      sessionDetailLoading = null
    }
  }

  async function deleteSession(sessionId: string) {
    deletingSessionId = sessionId
    sessionsError = null
    try {
      const { error } = await client.DELETE("/api/chat/sessions/{session_id}", {
        params: { path: { session_id: sessionId } },
      })
      if (error) {
        sessionsError = createKilnError(error)
        return
      }
      sessionRows = sessionRows.filter((r) => r.id !== sessionId)
      posthog.capture("chat_history_session_deleted")
    } catch (e) {
      sessionsError = createKilnError(e)
    } finally {
      deletingSessionId = null
    }
  }

  $: subtitle =
    visibleRows.length > 0
      ? `${visibleRows.length} conversation${visibleRows.length === 1 ? "" : "s"}`
      : null
</script>

<Dialog
  bind:this={historyDialog}
  title="Chat History"
  sub_subtitle={sessionsLoading ? null : subtitle}
  action_buttons={[]}
  on:close={resetAfterClose}
>
  <div class="max-h-[min(60vh,520px)] overflow-y-auto -mx-1 px-1">
    {#if sessionsLoading}
      <div
        class="flex flex-col items-center justify-center min-h-[120px] px-2 py-8"
        aria-busy="true"
        aria-label="Loading conversations"
      >
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if sessionsError}
      <div class="text-sm text-error px-2 py-4">
        {#if sessionsError.getCode() === CHAT_CLIENT_VERSION_TOO_OLD}
          <p>A newer version of Kiln is required.</p>
          <a
            href="/settings/check_for_update"
            class="underline font-medium hover:text-error/80 mt-1 inline-block"
            >Check for updates</a
          >
        {:else}
          <p>{sessionsError.getMessage()}</p>
        {/if}
      </div>
    {:else if visibleRows.length === 0}
      <div class="flex flex-col items-center justify-center py-10 px-4">
        <div class="w-10 h-10 text-base-content/15 mb-3">
          <ChatIcon />
        </div>
        <p class="text-sm font-medium text-base-content/70">
          No conversations yet
        </p>
        <p class="text-xs text-base-content/40 mt-1">
          Start a chat to see it saved here
        </p>
      </div>
    {:else}
      {@const busy =
        sessionDetailLoading !== null || deletingSessionId !== null}
      {#if activeNodes.length > 0}
        <div
          class="px-3 pt-1 pb-1 text-xs font-semibold uppercase tracking-wide text-primary/90"
        >
          Working now
        </div>
        <div class="flex flex-col gap-0.5">
          {#each activeNodes as node (node.row.id)}
            <ChatHistoryRow
              row={node.row}
              loading={sessionDetailLoading === node.row.id}
              deleting={deletingSessionId === node.row.id}
              {busy}
              onSelect={selectSession}
              onDelete={deleteSession}
            />
            {#each node.children as child (child.id)}
              <div class="pl-5">
                <ChatHistoryRow
                  row={child}
                  loading={sessionDetailLoading === child.id}
                  deleting={deletingSessionId === child.id}
                  {busy}
                  onSelect={selectSession}
                  onDelete={deleteSession}
                />
              </div>
            {/each}
          {/each}
        </div>
        {#if recentNodes.length > 0}
          <div class="divider my-1.5"></div>
          <div
            class="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-base-content/40"
          >
            Recent
          </div>
        {/if}
      {/if}
      <div class="flex flex-col gap-0.5">
        {#each recentNodes as node (node.row.id)}
          <ChatHistoryRow
            row={node.row}
            loading={sessionDetailLoading === node.row.id}
            deleting={deletingSessionId === node.row.id}
            {busy}
            onSelect={selectSession}
            onDelete={deleteSession}
          />
          {#each node.children as child (child.id)}
            <div class="pl-5">
              <ChatHistoryRow
                row={child}
                loading={sessionDetailLoading === child.id}
                deleting={deletingSessionId === child.id}
                {busy}
                onSelect={selectSession}
                onDelete={deleteSession}
              />
            </div>
          {/each}
        {/each}
      </div>
    {/if}
  </div>
</Dialog>
