import { get, writable, derived } from "svelte/store"
import { base_url, client } from "$lib/api_client"
import type { LogMessage, RagConfigWithSubConfigs, RagProgress } from "../types"
import { createKilnError, type KilnError } from "../utils/error_handlers"
import { progress_ui_state } from "./progress_ui_store"

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
  is_archived: Record<string, boolean>
  error: KilnError | null
  last_started_rag_config_id: string | null
}

export const ragProgressStore = createRagProgressStore()

export const allRagConfigs = derived(ragProgressStore, ($store) => {
  return sortRagConfigs(Object.values($store.rag_configs), "created_at")
})

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

    // rag configuration id -> is_archived
    is_archived: {},

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
    // retrieve all rag configs
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

    for (const rag_config of data) {
      if (!rag_config.id) {
        continue
      }
      // skip archived configs
      if (rag_config.is_archived) {
        continue
      }
      run_rag_config(project_id, rag_config.id)
    }

    return true
  }

  function run_rag_config(project_id: string, rag_config_id: string): boolean {
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

    const run_url = `${base_url}/api/projects/${project_id}/rag_configs/${rag_config_id}/run`
    const eventSource = new EventSource(run_url)

    eventSource.onmessage = (event) => {
      try {
        // complete is a special message part of SSE to indicate the run is complete
        // it does not mean the run was successful
        if (event.data === "complete") {
          eventSource.close()

          // the run may have failed before even sending any explicit errors for any of the steps
          // for example if the run failed before even starting (e.g. invalid config)

          const state = get(ragProgressStore)
          const previous_progress_state = state.progress[rag_config_id]
          const extraction_incomplete =
            (previous_progress_state.total_document_extracted_count ?? 0) <
            previous_progress_state.total_document_count
          const chunking_incomplete =
            (previous_progress_state.total_document_chunked_count ?? 0) <
            previous_progress_state.total_document_count
          const embedding_incomplete =
            (previous_progress_state.total_document_embedded_count ?? 0) <
            previous_progress_state.total_document_count
          const indexing_incomplete =
            (previous_progress_state.total_chunk_completed_count ?? 0) <
            previous_progress_state.total_chunk_count

          const failed_implicitly =
            (previous_progress_state.total_document_count ?? 0) > 0 &&
            (extraction_incomplete ||
              chunking_incomplete ||
              embedding_incomplete ||
              indexing_incomplete)

          const completion_status =
            has_errors(rag_config_id) || failed_implicitly
              ? "completed_with_errors"
              : "complete"

          update((state) => {
            return {
              ...state,
              running_rag_configs: {
                ...state.running_rag_configs,
                [rag_config_id]: false,
              },
              status: {
                ...state.status,
                [rag_config_id]: completion_status,
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
              cta: has_errors(rag_config_id) ? "View Errors" : "View Results",
              progress: 100,
              step_count: null,
              current_step: 0,
            })
          }
        } else {
          const payload = JSON.parse(event.data) as RagProgress
          update((state) => {
            const currentLogs = state.logs[rag_config_id] || []
            const newLogs = payload.logs || []

            return {
              ...state,
              progress: {
                ...state.progress,
                [rag_config_id]: payload,
              },
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
        }
      } catch (error) {
        console.error(
          `Error processing SSE message while running RAG config ${rag_config_id}: ${error}`,
        )
        eventSource.close()
        update((state) => ({
          ...state,
          status: { ...state.status, [rag_config_id]: "completed_with_errors" },
          running_rag_configs: {
            ...state.running_rag_configs,
            [rag_config_id]: false,
          },
          logs: {
            ...state.logs,
            [rag_config_id]: [
              ...(state.logs[rag_config_id] || []),
              {
                level: "error",
                message: `Error running RAG config: ${error}`,
              },
            ],
          },
        }))

        if (
          get(ragProgressStore).last_started_rag_config_id === rag_config_id
        ) {
          progress_ui_state.set({
            title: "Processing Documents",
            body: "",
            link: `/docs/rag_configs/${project_id}`,
            cta: "View Errors",
            progress: 100,
            step_count: null,
            current_step: null,
          })
        }
      }
    }

    // Don't restart on an error (default SSE behavior)
    eventSource.onerror = (error) => {
      console.error(
        `Error on SSE connection while running RAG config ${rag_config_id}: ${error}`,
      )
      eventSource.close()
      update((state) => ({
        ...state,
        status: { ...state.status, [rag_config_id]: "completed_with_errors" },
        running_rag_configs: {
          ...state.running_rag_configs,
          [rag_config_id]: false,
        },
        logs: {
          ...state.logs,
          [rag_config_id]: [
            ...(state.logs[rag_config_id] || []),
            {
              level: "error",
              message: `SSE connection error: ${error}`,
            },
          ],
        },
      }))
      if (get(ragProgressStore).last_started_rag_config_id === rag_config_id) {
        progress_ui_state.set({
          title: "Processing Documents",
          body: "",
          link: `/docs/rag_configs/${project_id}`,
          cta: "View Errors",
          progress: 100,
          step_count: null,
          current_step: null,
        })
      }
    }

    return true
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
        is_archived: {},
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
        is_archived: {
          ...state.is_archived,
          ...rag_configs_response.reduce(
            (acc, rag_config) => {
              acc[String(rag_config.id)] = rag_config.is_archived
              return acc
            },
            {} as Record<string, boolean>,
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

export async function update_rag_config_archived_state(
  rag_config_id: string,
  is_archived: boolean,
) {
  ragProgressStore.update((state) => ({
    ...state,
    is_archived: {
      ...state.is_archived,
      [rag_config_id]: is_archived,
    },
  }))
}
