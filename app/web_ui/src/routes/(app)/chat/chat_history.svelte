<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import { client } from "$lib/api_client"
  import { hydrateSessionFromSnapshot } from "$lib/chat/session_messages"
  import type { LoadedChatSessionDetail } from "$lib/chat/chat_history_apply"
  import type { components } from "$lib/api_schema"
  import { createKilnError } from "$lib/utils/error_handlers"

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

  function onGlobalKeydown(e: KeyboardEvent) {
    if (!visible) return
    if (e.key === "Escape") {
      e.preventDefault()
      close()
    }
  }
</script>

<svelte:window on:keydown={onGlobalKeydown} />

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
        <div class="flex-1 min-h-0 overflow-y-auto px-2 py-2">
          {#if sessionsLoading}
            <p class="text-sm text-base-content/60 px-2 py-4 text-center">
              Loading…
            </p>
          {:else if sessionsError}
            <p class="text-sm text-error px-2 py-4">{sessionsError}</p>
          {:else if sessionRows.length === 0}
            <p class="text-sm text-base-content/60 px-2 py-4 text-center">
              No sessions yet.
            </p>
          {:else}
            <ul class="menu menu-sm rounded-lg w-full">
              {#each sessionRows as row (row.id)}
                <li>
                  <button
                    type="button"
                    class="text-left w-full rounded-lg"
                    disabled={sessionDetailLoading !== null}
                    on:click={() => selectSession(row.id)}
                  >
                    <span class="truncate">{displayTitle(row)}</span>
                    {#if sessionDetailLoading === row.id}
                      <span class="loading loading-spinner loading-xs ml-2"
                      ></span>
                    {/if}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}
