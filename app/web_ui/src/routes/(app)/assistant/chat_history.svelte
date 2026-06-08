<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import posthog from "posthog-js"
  import { client } from "$lib/api_client"
  import { hydrateSessionFromSnapshot } from "$lib/chat/session_messages"
  import type { LoadedChatSessionDetail } from "$lib/chat/chat_history_apply"
  import {
    splitSessionRows,
    type SessionListItem,
  } from "$lib/chat/session_grouping"
  import { auto_run_store } from "$lib/chat/auto_run_store"
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

  $: ({ active: activeRows, recent: recentRows } =
    splitSessionRows(sessionRows))

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
      const { messages, continuationTraceId } =
        hydrateSessionFromSnapshot(snapshot)
      dispatch("apply", { messages, continuationTraceId })
      posthog.capture("chat_history_session_loaded", {
        message_count: messages.length,
        auto_active: !!row.auto_active,
      })
      // Re-attach the live auto run after hydrating completed history. The
      // runner replays the in-progress turn so there is no visible gap; if it
      // has finished or is gone, the events stream lands cleanly in the "off"
      // state (ui_design §5).
      if (row.auto_active && row.auto_run_id) {
        auto_run_store.attach(row.auto_run_id)
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
    sessionRows.length > 0
      ? `${sessionRows.length} conversation${sessionRows.length === 1 ? "" : "s"}`
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
    {:else if sessionRows.length === 0}
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
      {#if activeRows.length > 0}
        <div
          class="px-3 pt-1 pb-1 text-xs font-semibold uppercase tracking-wide text-primary/90"
        >
          Working now
        </div>
        <div class="flex flex-col gap-0.5">
          {#each activeRows as row (row.id)}
            <ChatHistoryRow
              {row}
              loading={sessionDetailLoading === row.id}
              deleting={deletingSessionId === row.id}
              {busy}
              onSelect={selectSession}
              onDelete={deleteSession}
            />
          {/each}
        </div>
        {#if recentRows.length > 0}
          <div class="divider my-1.5"></div>
          <div
            class="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-base-content/40"
          >
            Recent
          </div>
        {/if}
      {/if}
      <div class="flex flex-col gap-0.5">
        {#each recentRows as row (row.id)}
          <ChatHistoryRow
            {row}
            loading={sessionDetailLoading === row.id}
            deleting={deletingSessionId === row.id}
            {busy}
            onSelect={selectSession}
            onDelete={deleteSession}
          />
        {/each}
      </div>
    {/if}
  </div>
</Dialog>
