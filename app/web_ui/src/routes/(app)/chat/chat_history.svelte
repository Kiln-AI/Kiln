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

  /** Called before the modal opens (e.g. abort in-flight stream). */
  export let onBeforeOpen: (() => void) | undefined = undefined

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
  let openDropdownId: string | null = null

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
    onBeforeOpen?.()
    historyDialog?.show()
    void loadSessionList()
  }

  function resetAfterClose() {
    sessionsError = null
    openDropdownId = null
  }

  function close() {
    historyDialog?.close()
  }

  function onDialogCancel(e: CustomEvent<Event>) {
    if (openDropdownId) {
      e.detail.preventDefault()
      openDropdownId = null
    }
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
      openDropdownId = null
    }
  }

  function toggleDropdown(e: Event, sessionId: string) {
    e.stopPropagation()
    openDropdownId = openDropdownId === sessionId ? null : sessionId
  }

  function onGlobalClick() {
    if (openDropdownId) openDropdownId = null
  }

  $: subtitle =
    sessionRows.length > 0
      ? `${sessionRows.length} conversation${sessionRows.length === 1 ? "" : "s"}`
      : null
</script>

<svelte:window on:click={onGlobalClick} />

<Dialog
  bind:this={historyDialog}
  title="Chat History"
  sub_subtitle={sessionsLoading ? null : subtitle}
  action_buttons={[]}
  on:close={resetAfterClose}
  on:cancel={onDialogCancel}
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
              <div class="relative shrink-0">
                <button
                  type="button"
                  class="btn btn-xs btn-circle btn-ghost opacity-0 group-hover:opacity-100 transition-opacity"
                  on:click|stopPropagation={(e) => toggleDropdown(e, row.id)}
                  aria-label="Session options"
                >
                  <svg
                    class="h-4 w-4"
                    viewBox="0 0 16 16"
                    fill="currentColor"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                  >
                    <circle cx="8" cy="3" r="1.5" />
                    <circle cx="8" cy="8" r="1.5" />
                    <circle cx="8" cy="13" r="1.5" />
                  </svg>
                </button>
                {#if openDropdownId === row.id}
                  <div
                    class="absolute right-0 top-full mt-1 z-20 rounded-lg bg-base-100 shadow-lg border border-base-content/10 py-1 min-w-[120px]"
                  >
                    <button
                      type="button"
                      class="flex items-center gap-2 w-full px-3 py-1.5 text-sm text-error hover:bg-base-200 transition-colors"
                      on:click|stopPropagation={() => deleteSession(row.id)}
                    >
                      <svg
                        class="h-4 w-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        aria-hidden="true"
                      >
                        <path
                          d="M6 7V18C6 19.1046 6.89543 20 8 20H16C17.1046 20 18 19.1046 18 18V7M6 7H5M6 7H8M18 7H19M18 7H16M10 11V16M14 11V16M8 7V5C8 3.89543 8.89543 3 10 3H14C15.1046 3 16 3.89543 16 5V7M8 7H16"
                          stroke="currentColor"
                          stroke-width="1.5"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                      Delete
                    </button>
                  </div>
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</Dialog>
