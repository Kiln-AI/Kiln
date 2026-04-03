<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import { client } from "$lib/api_client"
  import { hydrateSessionFromSnapshot } from "$lib/chat/session_messages"
  import type { LoadedChatSessionDetail } from "$lib/chat/chat_history_apply"
  import type { components } from "$lib/api_schema"
  import { createKilnError } from "$lib/utils/error_handlers"
  import { formatDate } from "$lib/utils/formatters"

  /** Called before the modal opens (e.g. abort in-flight stream). */
  export let onBeforeOpen: (() => void) | undefined = undefined

  const dispatch = createEventDispatcher<{
    apply: LoadedChatSessionDetail
  }>()

  type SessionListItem = components["schemas"]["ChatSessionListItem"]

  let visible = false
  let sessionsLoading = false
  let sessionsError: string | null = null
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
        sessionsError = createKilnError(error).getMessage()
        return
      }
      sessionRows = data ?? []
    } catch (e) {
      sessionsError = createKilnError(e).getMessage()
    } finally {
      sessionsLoading = false
    }
  }

  export function open() {
    onBeforeOpen?.()
    visible = true
    void loadSessionList()
  }

  function close() {
    visible = false
    sessionsError = null
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
        sessionsError = createKilnError(error).getMessage()
        return
      }
      const { messages, continuationTraceId } =
        hydrateSessionFromSnapshot(snapshot)
      dispatch("apply", { messages, continuationTraceId })
      close()
    } catch (e) {
      sessionsError = createKilnError(e).getMessage()
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
        sessionsError = createKilnError(error).getMessage()
        return
      }
      sessionRows = sessionRows.filter((r) => r.id !== sessionId)
    } catch (e) {
      sessionsError = createKilnError(e).getMessage()
    } finally {
      deletingSessionId = null
      openDropdownId = null
    }
  }

  function toggleDropdown(e: Event, sessionId: string) {
    e.stopPropagation()
    openDropdownId = openDropdownId === sessionId ? null : sessionId
  }

  function onGlobalKeydown(e: KeyboardEvent) {
    if (!visible) return
    if (e.key === "Escape") {
      if (openDropdownId) {
        openDropdownId = null
        e.preventDefault()
        return
      }
      e.preventDefault()
      close()
    }
  }

  function onGlobalClick() {
    if (openDropdownId) openDropdownId = null
  }
</script>

<svelte:window on:keydown={onGlobalKeydown} on:click={onGlobalClick} />

{#if visible}
  <div
    class="fixed inset-0 z-[100] flex flex-col min-h-0"
    role="dialog"
    aria-modal="true"
    aria-label="Chat history"
  >
    <button
      type="button"
      class="absolute inset-0 bg-base-content/40 border-0 cursor-default"
      on:click={close}
      aria-label="Close history"
    ></button>
    <div
      class="relative z-10 flex flex-1 min-h-0 items-stretch justify-center p-3 sm:p-4 pointer-events-none"
    >
      <div
        class="pointer-events-auto flex flex-col w-full max-w-lg max-h-[min(80vh,640px)] rounded-2xl bg-base-100 shadow-xl border border-base-content/10 my-auto"
      >
        <div
          class="flex items-center justify-between gap-2 px-4 py-3 border-b border-base-content/10 shrink-0"
        >
          <span class="font-medium text-base">Past conversations</span>
          <button
            type="button"
            class="btn btn-sm btn-circle btn-ghost"
            on:click={close}
            aria-label="Close"
          >
            <svg
              class="h-5 w-5"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M7 7L17 17M7 17L17 7"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto px-3 py-2">
          {#if sessionsLoading}
            <p class="text-sm text-base-content/60 px-2 py-4 text-center">
              Loading…
            </p>
          {:else if sessionsError}
            <p class="text-sm text-error px-2 py-4">{sessionsError}</p>
          {:else if sessionRows.length === 0}
            <p class="text-sm text-base-content/60 px-2 py-4 text-center">
              No conversations yet.
            </p>
          {:else}
            <div class="flex flex-col gap-1.5">
              {#each sessionRows as row (row.id)}
                <div
                  class="group relative flex items-center w-full rounded-xl px-3 py-2.5 text-left transition-colors bg-base-200/50 hover:bg-base-200"
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
                    {#if row.updated_at}
                      <span class="block text-xs text-gray-500 mt-0.5"
                        >{formatDate(row.updated_at)}</span
                      >
                    {/if}
                  </div>
                  {#if sessionDetailLoading === row.id || deletingSessionId === row.id}
                    <span class="loading loading-spinner loading-xs shrink-0"
                    ></span>
                  {:else}
                    <div class="relative shrink-0">
                      <button
                        type="button"
                        class="btn btn-xs btn-circle btn-ghost opacity-0 group-hover:opacity-100 transition-opacity"
                        on:click|stopPropagation={(e) =>
                          toggleDropdown(e, row.id)}
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
                            on:click|stopPropagation={() =>
                              deleteSession(row.id)}
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
      </div>
    </div>
  </div>
{/if}
