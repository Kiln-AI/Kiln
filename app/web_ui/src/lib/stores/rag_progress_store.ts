import { get, writable, derived } from "svelte/store"
import { base_url, client } from "$lib/api_client"
import type { LogMessage, RagConfigWithSubConfigs, RagProgress } from "../types"
import { createKilnError, type KilnError } from "../utils/error_handlers"
import { progress_ui_state } from "./progress_ui_store"
import { Semaphore } from "$lib/utils/semaphore"

const MAX_CONCURRENT_RAG_CONFIGS = 2

export type RagConfigurationStatus =
  | "not_started"
  | "incomplete"
  | "running"
  | "complete"
  | "completed_with_errors"

interface RagConfigurationProgressState {
  rag_configs: Record<string, RagConfigWithSubConfigs>
  progress: Record<string, RagProgress>
  logs: Record<string, LogMessage[]>
  status: Record<string, RagConfigurationStatus>
  running_rag_configs: Record<string, boolean>
  error: KilnError | null
  last_started_rag_config_id: string | null
}

export const ragProgressStore = createRagProgressStore()

export const allRagConfigs = derived(ragProgressStore, ($store) => {
  return sortRagConfigs(Object.values($store.rag_configs), "created_at")
})

// cap concurrent EventSource connections browsers have different limits,
// we keep the limit low enough to be safe for most browsers
const sseSlots = new Semaphore(MAX_CONCURRENT_RAG_CONFIGS)

function createRagProgressStore() {
  const { subscribe, set, update } = writable<RagConfigurationProgressState>({
    // rag configuration id -> rag config
    rag_configs: {},

    // rag configuration id -> progress; only applies to rag configurations that are running
    progress: {},

    // rag configuration id -> logs
    logs: {},

    // rag configuration id -> status
    status: {},

    // rag configuration id -> is_running
    running_rag_configs: {},

    // error
    error: null,

    // last started rag config id
    last_started_rag_config_id: null,
  })

  function has_errors(rag_config_id: string): boolean {
    const progress = get(ragProgressStore).progress[rag_config_id]
    if (!progress) return false
    return (
      (progress.total_document_extracted_error_count ?? 0) > 0 ||
      (progress.total_document_chunked_error_count ?? 0) > 0 ||
      (progress.total_document_embedded_error_count ?? 0) > 0 ||
      (progress.total_chunks_indexed_error_count ?? 0) > 0
    )
  }

  async function run_all_rag_configs(project_id: string): Promise<boolean> {
    // get all rag configs
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/rag_configs",
      {
        params: {
          path: {
            project_id,
          },
        },
      },
    )

    if (error) {
      return false
    }

    // process rag configs with concurrency limit to avoid hitting browser limits
    const tasks: Promise<unknown>[] = []
    for (const rag_config of data) {
      if (!rag_config.id) {
        continue
      }

      tasks.push(
        (async () => {
          await sseSlots.acquire()
          try {
            await run_rag_config(project_id, String(rag_config.id))
          } finally {
            sseSlots.release()
          }
        })(),
      )
    }

    const results = await Promise.allSettled(tasks)
    const failed = results.filter((r) => r.status === "rejected")
    return failed.length === 0
  }

  async function run_rag_config(
    project_id: string,
    rag_config_id: string,
  ): Promise<void> {
    // we update the status even if waiting for slot, so that it looks
    // like it is running to the user
    update((state) => ({
      ...state,
      status: { ...state.status, [rag_config_id]: "running" },
      running_rag_configs: {
        ...state.running_rag_configs,
        [rag_config_id]: true,
      },
      logs: {
        ...state.logs,
        [rag_config_id]: [],
      },
      last_started_rag_config_id: rag_config_id,
    }))

    // lets us track the last started rag config progress
    progress_ui_state.set({
      title: "Processing Documents",
      body: "",
      link: `/docs/rag_configs/${project_id}`,
      cta: "View Progress",
      progress: 0,
      step_count: null,
      current_step: 0,
    })

    // we will send a log to say that the config is queued if we are still blocked for more than 10s
    // otherwise, if the config starts in less than 10s, we won't show anything
    let showed_queued_log = false
    let wait_log_timer: ReturnType<typeof setTimeout> | null = setTimeout(
      () => {
        showed_queued_log = true
        update((state) => ({
          ...state,
          logs: {
            ...state.logs,
            [rag_config_id]: [
              ...(state.logs[rag_config_id] ?? []),
              {
                level: "info",
                message: `A maximum of ${MAX_CONCURRENT_RAG_CONFIGS} configs can run at the same time. This config is queued and will start automatically when a slot is free. Refreshing the browser window will cancel the queue and any config that is currently running or waiting to start.`,
              },
            ],
          },
        }))
      },
      10_000,
    )

    await sseSlots.acquire()
    // if we got a slot within 10s, prevent the log from being added
    if (wait_log_timer) {
      clearTimeout(wait_log_timer)
      wait_log_timer = null
    }

    if (showed_queued_log) {
      update((state) => ({
        ...state,
        logs: {
          ...state.logs,
          [rag_config_id]: [
            ...(state.logs[rag_config_id] ?? []),
            { level: "info", message: "Started running" },
          ],
        },
      }))
    }

    try {
      await run_rag_config_unsafe(project_id, rag_config_id)
    } finally {
      sseSlots.release()
    }
  }

  function run_rag_config_unsafe(
    project_id: string,
    rag_config_id: string,
  ): Promise<void> {
    const run_url = `${base_url}/api/projects/${project_id}/rag_configs/${rag_config_id}/run`
    const eventSource = new EventSource(run_url)

    return new Promise<void>((resolve) => {
      const finalize = (status: RagConfigurationStatus) => {
        try {
          eventSource.close()
        } catch (error) {
          console.error("Error closing event source", error)
        }
        update((state) => ({
          ...state,
          running_rag_configs: {
            ...state.running_rag_configs,
            [rag_config_id]: false,
          },
          status: { ...state.status, [rag_config_id]: status },
        }))
        if (
          get(ragProgressStore).last_started_rag_config_id === rag_config_id
        ) {
          progress_ui_state.set({
            title: "Processing Documents",
            body: "",
            link: `/docs/rag_configs/${project_id}`,
            cta:
              status === "completed_with_errors"
                ? "View Errors"
                : "View Results",
            progress: 100,
            step_count: null,
            current_step: 0,
          })
        }

        // we don't need to reject because we handle errors in a more complex
        // and communicate it in the UI
        resolve()
      }

      eventSource.onmessage = (event) => {
        try {
          if (event.data === "complete") {
            const state = get(ragProgressStore)
            const prev = state.progress[rag_config_id]
            // guard for undefined
            if (!prev)
              return finalize(
                has_errors(rag_config_id)
                  ? "completed_with_errors"
                  : "complete",
              )
            const extraction_incomplete =
              (prev.total_document_extracted_count ?? 0) <
              (prev.total_document_count ?? 0)
            const chunking_incomplete =
              (prev.total_document_chunked_count ?? 0) <
              (prev.total_document_count ?? 0)
            const embedding_incomplete =
              (prev.total_document_embedded_count ?? 0) <
              (prev.total_document_count ?? 0)
            const indexing_incomplete =
              (prev.total_chunk_completed_count ?? 0) <
              (prev.total_chunk_count ?? 0)

            const failed_implicitly =
              (prev.total_document_count ?? 0) > 0 &&
              (extraction_incomplete ||
                chunking_incomplete ||
                embedding_incomplete ||
                indexing_incomplete)

            const completion_status =
              has_errors(rag_config_id) || failed_implicitly
                ? "completed_with_errors"
                : "complete"

            return finalize(completion_status)
          }

          const payload = JSON.parse(event.data) as RagProgress
          update((state) => {
            const currentLogs = state.logs[rag_config_id] || []
            const newLogs = payload.logs || []
            return {
              ...state,
              progress: { ...state.progress, [rag_config_id]: payload },
              logs: {
                ...state.logs,
                [rag_config_id]: [...currentLogs, ...newLogs],
              },
            }
          })

          if (
            get(ragProgressStore).last_started_rag_config_id === rag_config_id
          ) {
            progress_ui_state.set({
              title: "Processing Documents",
              body: "",
              link: `/docs/rag_configs/${project_id}`,
              cta: "View Progress",
              progress:
                (payload.total_document_completed_count /
                  Math.max(payload.total_document_count, 1)) *
                100,
              step_count: null,
              current_step: null,
            })
          }
        } catch (err) {
          update((state) => ({
            ...state,
            logs: {
              ...state.logs,
              [rag_config_id]: [
                ...(state.logs[rag_config_id] || []),
                {
                  level: "error",
                  message: `Error running RAG config: ${String(err)}`,
                },
              ],
            },
          }))
          finalize("completed_with_errors")
        }
      }

      eventSource.onerror = (error) => {
        update((state) => ({
          ...state,
          logs: {
            ...state.logs,
            [rag_config_id]: [
              ...(state.logs[rag_config_id] || []),
              {
                level: "error",
                message: `SSE connection error: ${String(error)}`,
              },
            ],
          },
        }))
        finalize("completed_with_errors")
      }
    })
  }

  return {
    subscribe,
    set,
    update,
    run_all_rag_configs,
    run_rag_config,
    reset: () =>
      set({
        progress: {},
        status: {},
        logs: {},
        running_rag_configs: {},
        rag_configs: {},
        error: null,
        last_started_rag_config_id: null,
      }),
  }
}

function sortRagConfigs(
  rag_configs: RagConfigWithSubConfigs[],
  sortKey: keyof RagConfigWithSubConfigs = "created_at",
): RagConfigWithSubConfigs[] {
  return [...rag_configs].sort((a, b) => {
    const aValue = a[sortKey] || ""
    const bValue = b[sortKey] || ""
    if (!bValue) return 1
    if (!aValue) return -1
    if (bValue < aValue) return -1
    if (bValue > aValue) return 1
    return 0
  })
}

function calculateStatus(progress: RagProgress): RagConfigurationStatus {
  if (
    progress.total_document_completed_count === progress.total_document_count &&
    progress.total_chunk_completed_count === progress.total_chunk_count
  ) {
    return "complete"
  }

  const max_step_completion = Math.max(
    progress.total_document_extracted_count,
    progress.total_document_chunked_count,
    progress.total_document_embedded_count,
    progress.total_chunks_indexed_count,
  )
  if (max_step_completion === 0) {
    return "not_started"
  }

  const min_step_completion = Math.min(
    progress.total_document_extracted_count,
    progress.total_document_chunked_count,
    progress.total_document_embedded_count,
  )
  if (min_step_completion < progress.total_document_count) {
    return "incomplete"
  }

  const has_errors = [
    progress.total_document_extracted_error_count,
    progress.total_document_chunked_error_count,
    progress.total_document_embedded_error_count,
    progress.total_chunks_indexed_error_count,
  ].some((count) => count > 0)
  if (has_errors) {
    return "completed_with_errors"
  }

  // indexing is tracked in terms of chunks, not documents
  if (progress.total_chunks_indexed_count < progress.total_chunk_count) {
    return "incomplete"
  }

  return "complete"
}

export const formatProgressPercentage = (progress: RagProgress): string => {
  if (progress.total_document_count === 0) {
    return "0%"
  }

  return `${((progress.total_document_completed_count / progress.total_document_count) * 100).toFixed(0)}%`
}

export async function load_all_rag_config_progress(projectId: string) {
  try {
    const { data, error } = await client.POST(
      "/api/projects/{project_id}/rag_configs/progress",
      {
        params: {
          path: {
            project_id: projectId,
          },
        },
        body: {},
      },
    )

    if (!error && data) {
      for (const [rag_config_id, progress] of Object.entries(data)) {
        ragProgressStore.update((state) => {
          const newProgress = {
            ...state.progress,
            [rag_config_id]: {
              ...state.progress[rag_config_id],
              ...progress,
            },
          }

          // we need to make sure not to overwrite the client-side status, otherwise we will
          // lose the progress state when navigating out and back into the pages that
          const newStatus = {
            ...state.status,
            [rag_config_id]:
              state.status[rag_config_id] ||
              calculateStatus(newProgress[rag_config_id]),
          }

          return {
            ...state,
            progress: newProgress,
            status: newStatus,
          }
        })
      }
    }
  } catch (e) {
    ragProgressStore.update((state) => ({
      ...state,
      error: createKilnError(e),
    }))
  }
}

export async function load_rag_configs(project_id: string) {
  try {
    if (!project_id) {
      throw new Error("Project ID not set.")
    }
    const { data: rag_configs_response, error: get_error } = await client.GET(
      "/api/projects/{project_id}/rag_configs",
      {
        params: {
          path: {
            project_id,
          },
        },
      },
    )
    if (get_error) {
      throw get_error
    }
    ragProgressStore.update((state) => {
      const newState = {
        ...state,
        rag_configs: {
          ...state.rag_configs,
          ...rag_configs_response.reduce(
            (acc, rag_config) => {
              acc[String(rag_config.id)] = rag_config
              return acc
            },
            {} as Record<string, RagConfigWithSubConfigs>,
          ),
        },
      }
      return newState
    })
  } catch (e) {
    ragProgressStore.update((state) => ({
      ...state,
      error: createKilnError(e),
    }))
  }
}
