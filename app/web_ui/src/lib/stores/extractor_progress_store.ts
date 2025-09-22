import { writable } from "svelte/store"
import { base_url, client } from "$lib/api_client"

type ExtractorStatus =
  | "not_started"
  | "incomplete"
  | "complete"
  | "running"
  | "completed_with_errors"

type UiExtractionProgress = {
  success: number
  total: number
  is_running?: boolean // we only know this while running
  error?: number // we only know this while running
}

interface ExtractorProgressState {
  progress: Record<string, UiExtractionProgress>
  status: Record<string, ExtractorStatus>
}

function createExtractorProgressStore() {
  const { subscribe, set, update } = writable<ExtractorProgressState>({
    // extractor config id -> progress | only applies to extractor configs that are running
    progress: {},

    // extractor config id -> status
    status: {},
  })

  async function getProgress(projectId: string, extractorConfigId: string) {
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}/progress",
        {
          params: {
            path: {
              project_id: projectId,
              extractor_config_id: extractorConfigId,
            },
          },
        },
      )
      if (!error && data) {
        update((state) => {
          const newProgress = {
            ...state.progress,
            [extractorConfigId]: {
              success: data.document_count_successful,
              total: data.document_count_total,
            },
          }
          const newStatus = {
            ...state.status,
            [extractorConfigId]: calculateStatus(
              newProgress[extractorConfigId],
            ),
          }
          return { progress: newProgress, status: newStatus }
        })
      }
    } catch (e) {
      // ignore progress errors for now
    }
  }

  function run_extractor(
    project_id: string,
    extractor_config_id: string,
  ): boolean {
    let extracted_count = 0
    let total_count = 0
    let error_count = 0

    const run_url = `${base_url}/api/projects/${project_id}/extractor_configs/${extractor_config_id}/run_extractor_config`
    update((state) => ({
      ...state,
      status: { ...state.status, [extractor_config_id]: "running" },
    }))

    const eventSource = new EventSource(run_url)

    eventSource.onmessage = (event) => {
      try {
        if (event.data === "complete") {
          eventSource.close()
          const newStatus =
            error_count > 0 ? "completed_with_errors" : "complete"
          extractorProgressStore.updateStatus(extractor_config_id, newStatus)
        } else {
          const data = JSON.parse(event.data)
          extracted_count = data.progress
          total_count = data.total
          error_count = data.errors
          extractorProgressStore.updateProgress(extractor_config_id, {
            is_running: true,
            success: extracted_count,
            total: total_count,
            error: error_count,
          })
          extractorProgressStore.updateStatus(extractor_config_id, "running")
        }
      } catch (error) {
        eventSource.close()
        extractorProgressStore.updateStatus(
          extractor_config_id,
          "completed_with_errors",
        )
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      extractorProgressStore.updateStatus(extractor_config_id, "incomplete")
    }

    return true
  }

  return {
    subscribe,
    set,
    update,
    run_extractor,
    getProgress,
    getAllProgress: async (projectId: string, extractorConfigIds: string[]) => {
      await Promise.all(
        extractorConfigIds.map((id) => getProgress(projectId, id)),
      )
    },
    updateStatus: (extractorConfigId: string, status: ExtractorStatus) => {
      update((state) => ({
        ...state,
        status: { ...state.status, [extractorConfigId]: status },
      }))
    },
    updateProgress: (
      extractorConfigId: string,
      progress: UiExtractionProgress,
    ) => {
      update((state) => {
        const newProgress = { ...state.progress, [extractorConfigId]: progress }
        const newStatus = {
          ...state.status,
          [extractorConfigId]: calculateStatus(progress),
        }
        return {
          progress: newProgress,
          status: newStatus,
        }
      })
    },
    reset: () =>
      set({
        progress: {},
        status: {},
      }),
  }
}

export const extractorProgressStore = createExtractorProgressStore()

function calculateStatus(progress: UiExtractionProgress): ExtractorStatus {
  if (progress.is_running) {
    return "running"
  }

  if (progress.success === 0) {
    return "not_started"
  }

  if (progress.success < progress.total) {
    return "incomplete"
  }

  return "complete"
}

export const formatProgressPercentage = (
  progress: UiExtractionProgress,
): string => {
  if (progress.total === 0) {
    return "0%"
  }

  return `${((progress.success / progress.total) * 100).toFixed(0)}%`
}
