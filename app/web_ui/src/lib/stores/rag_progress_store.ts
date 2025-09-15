import { get, writable, derived } from "svelte/store"
import { base_url, client } from "$lib/api_client"
import type {
  LogMessage,
  RagConfigWithSubConfigs,
  RagStepRunnerProgress,
  RagStepRunnerStatus,
  RagWorkflowStepNames,
} from "../types"
import { createKilnError, type KilnError } from "../utils/error_handlers"
import { progress_ui_state } from "./progress_ui_store"

export type RagConfigurationStatus =
  | "not_started"
  | "pending"
  | "running"
  | "incomplete"
  | "complete"
  | "completed_with_errors"

export type StepProgress = {
  step_name: RagWorkflowStepNames
  status: RagStepRunnerStatus
  expected_count: number | null
  success_count: number | null
  error_count: number | null
}

interface RagConfigurationProgressState {
  rag_configs: Record<string, RagConfigWithSubConfigs>
  orchestration_progress: Record<string, StepProgress>
  substep_progress: Record<string, Record<RagWorkflowStepNames, StepProgress>>
  logs: Record<string, LogMessage[]>
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

    // rag configuration id -> orchestration progress; only applies to rag configurations that are running
    orchestration_progress: {},

    // rag configuration id -> stepname -> substep progress; only applies to rag configurations that are running
    substep_progress: {},

    // rag configuration id -> logs
    logs: {},

    // error
    error: null,

    // last started rag config id
    last_started_rag_config_id: null,
  })

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
      run_rag_config(project_id, rag_config.id)
    }

    return true
  }

  function run_rag_config(project_id: string, rag_config_id: string): boolean {
    update((state) => ({
      ...state,
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
        if (event.data === "complete") {
          eventSource.close()
          update((state) => {
            return {
              ...state,
            }
          })

          if (
            get(ragProgressStore).last_started_rag_config_id === rag_config_id
          ) {
            progress_ui_state.set({
              title: "Processing Documents",
              body: "",
              link: `/docs/rag_configs/${project_id}`,
              cta:
                get(ragProgressStore).orchestration_progress[rag_config_id]
                  .status === "completed_with_errors"
                  ? "View Errors"
                  : "View Results",
              progress: 100,
              step_count: null,
              current_step: 0,
            })
          }
        } else {
          const payload = JSON.parse(event.data) as RagStepRunnerProgress
          update((state) => {
            const currentLogs = state.logs[rag_config_id] || []
            const newLogs = payload.logs || []

            if (payload.step_name === "orchestration") {
              const newState = {
                ...state,
                orchestration_progress: {
                  ...state.orchestration_progress,
                  [rag_config_id]: {
                    step_name: payload.step_name,
                    status: payload.status,
                    expected_count: payload.expected_count ?? null,
                    success_count: payload.success_count ?? null,
                    error_count: payload.error_count ?? null,
                  },
                },
                logs: {
                  ...state.logs,
                  [rag_config_id]: [...currentLogs, ...newLogs],
                },
              }

              return newState
            }

            return {
              ...state,
              substep_progress: {
                ...state.substep_progress,
                [rag_config_id]: {
                  ...state.substep_progress[rag_config_id],
                  [payload.step_name]: {
                    step_name: payload.step_name,
                    status: payload.status,
                    expected_count: payload.expected_count ?? null,
                    success_count: payload.success_count ?? null,
                    error_count: payload.error_count ?? null,
                  },
                },
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
                ((payload.success_count ?? 0) /
                  Math.max(payload.expected_count ?? 1, 1)) *
                100,
              step_count: null,
              current_step: null,
            })
          }
        }
      } catch (error) {
        eventSource.close()
        update((state) => ({
          ...state,
          orchestration_progress: {
            ...state.orchestration_progress,
            [rag_config_id]: {
              step_name: "orchestration",
              status: "completed_with_errors",
              expected_count: null,
              success_count: null,
              error_count: null,
            },
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
      eventSource.close()
      update((state) => ({
        ...state,
        orchestration_progress: {
          ...state.orchestration_progress,
          [rag_config_id]: {
            step_name: "orchestration",
            status: "completed_with_errors",
            expected_count: null,
            success_count: null,
            error_count: null,
          },
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
        orchestration_progress: {},
        substep_progress: {},
        rag_configs: {},
        error: null,
        logs: {},
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

export const formatProgressPercentage = (
  progress: RagStepRunnerProgress,
): string => {
  if (progress.expected_count === 0) {
    return "0%"
  }

  return `${(((progress.success_count ?? 0) / (progress.expected_count || 1)) * 100).toFixed(0)}%`
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
          const orchestration_progress = {
            step_name: "orchestration" as RagWorkflowStepNames,
            status: progress.orchestration.status,
            expected_count: progress.orchestration.expected_count ?? null,
            success_count: progress.orchestration.success_count ?? null,
            error_count: progress.orchestration.error_count ?? null,
          }

          delete progress.orchestration
          const otherSteps = Object.entries(progress).reduce(
            (acc, [step_name, step_progress]) => {
              acc[step_name as RagWorkflowStepNames] = {
                step_name: step_name as RagWorkflowStepNames,
                status: step_progress.status,
                expected_count: step_progress.expected_count ?? null,
                success_count: step_progress.success_count ?? null,
                error_count: step_progress.error_count ?? null,
              }
              return acc
            },
            {} as Record<RagWorkflowStepNames, StepProgress>,
          )

          return {
            ...state,
            substep_progress: {
              ...state.substep_progress,
              [rag_config_id]: otherSteps,
            },
            orchestration_progress: {
              ...state.orchestration_progress,
              [rag_config_id]: orchestration_progress,
            },
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
