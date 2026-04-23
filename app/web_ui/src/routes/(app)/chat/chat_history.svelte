<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import { client } from "$lib/api_client"
  import { hydrateSessionFromSnapshot } from "$lib/chat/session_messages"
  import type { LoadedChatSessionDetail } from "$lib/chat/chat_history_apply"
  import type { components } from "$lib/api_schema"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"
  import { formatDate } from "$lib/utils/formatters"
  import Dialog from "$lib/ui/dialog.svelte"
  import ChatIcon from "$lib/ui/icons/chat_icon.svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"

  const dispatch = createEventDispatcher<{
    apply: LoadedChatSessionDetail
  }>()

  type SessionListItem = components["schemas"]["ChatSessionListItem"]

  let historyDialog: Dialog | null = null
  let sessionsLoading = false
  let sessionsError: KilnError | null = null
  let sessionRows: SessionListItem[] = []
  let sessionDetailLoading: string | null = null
  let deletingSessionId: string | null = null

  function displayTitle(item: SessionListItem): string {
    if (item.title) return item.title
    return item.id.length > 12 ? `${item.id.slice(0, 10)}…` : item.id
  }

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
    historyDialog?.show()
    void loadSessionList()
  }

  function resetAfterClose() {
    sessionsError = null
  }

  function close() {
    historyDialog?.close()
  }

  async function selectSession(sessionId: string) {
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
      <div class="flex flex-col gap-0.5">
        {#each sessionRows as row (row.id)}
          <div
            class="group relative flex items-center w-full rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-base-200/80 cursor-pointer"
            class:opacity-50={deletingSessionId === row.id}
            role="button"
            tabindex="0"
            on:click={() =>
              sessionDetailLoading === null &&
              deletingSessionId === null &&
              selectSession(row.id)}
            on:keydown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                if (!sessionDetailLoading && !deletingSessionId)
                  selectSession(row.id)
              }
            }}
          >
            <div class="flex-1 min-w-0">
              <span class="block text-sm font-medium truncate"
                >{displayTitle(row)}</span
              >
            </div>
            {#if sessionDetailLoading === row.id || deletingSessionId === row.id}
              <span class="loading loading-spinner loading-xs shrink-0 ml-2"
              ></span>
            {:else}
              {#if row.updated_at}
                <span
                  class="text-xs text-gray-500 shrink-0 ml-3 whitespace-nowrap"
                  >{formatDate(row.updated_at)}</span
                >
              {/if}
              <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
              <div
                class="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                on:click|stopPropagation
              >
                <TableActionMenu
                  width="w-40"
                  items={[
                    {
                      label: "Delete",
                      onclick: () => deleteSession(row.id),
                    },
                  ]}
                />
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</Dialog>
