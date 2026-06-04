import { get, writable, derived } from "svelte/store"
import { base_url, client } from "$lib/api_client"
import type { LogMessage, RagConfigWithSubConfigs, RagProgress } from "../types"
import { createKilnError, type KilnError } from "../utils/error_handlers"
import { progress_ui_state } from "./progress_ui_store"
import { jobs } from "./jobs_store"
import type { JobRecord } from "./jobs_api"
import { is_terminal } from "./job_status"
import { get_tag } from "./job_tags"

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

function getDefaultProjectState(): RagConfigurationProgressState {
  return {
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
  }
}

export const ragProgressStore = createRagProgressStore()

// Module-level reflector: any RAG-kind job in the project-scoped jobs store
// pushes its state into the rag progress store. Lets the configs list page
// pick up in-flight runs on refresh (and runs spawned from other sessions),
// not just runs initiated from the current tab. Subscribes once at import
// time and stays subscribed for the life of the SPA — there's no teardown
// path because there's no point in disconnecting.
function reflect_jobs_into_rag_store($jobs: JobRecord[]): void {
  // Group RAG jobs by project so each project's state updates atomically.
  const by_project = new Map<string, JobRecord[]>()
  for (const job of $jobs) {
    const tag = get_tag(job)
    if (tag?.kind !== "rag") continue
    if (!job.project_id) continue
    const list = by_project.get(job.project_id) ?? []
    list.push(job)
    by_project.set(job.project_id, list)
  }

  for (const [project_id, project_jobs] of by_project) {
    ragProgressStore.updateProjectState(project_id, (state) => {
      const progress = { ...state.progress }
      const logs = { ...state.logs }
      const status = { ...state.status }
      const running = { ...state.running_rag_configs }

      for (const job of project_jobs) {
        const tag = get_tag(job)
        if (tag?.kind !== "rag") continue
        const rag_config_id = tag.rag_config_id

        // Live progress / logs come from the worker's per-tick metadata
        // patch. Always overlay when present — the worker's snapshot is
        // strictly fresher than whatever load_all_rag_config_progress put
        // there at page-mount time.
        const rag_progress = (
          job.metadata as { rag_progress?: RagProgress } | null
        )?.rag_progress
        if (rag_progress) {
          progress[rag_config_id] = rag_progress
          logs[rag_config_id] = rag_progress.logs ?? []
        }

        if (!is_terminal(job.status)) {
          status[rag_config_id] = "running"
          running[rag_config_id] = true
        } else {
          running[rag_config_id] = false
          if (job.status === "succeeded") {
            const has_errs = (job.progress?.error ?? 0) > 0
            // Re-derive from the latest progress for the "succeeded but
            // silently incomplete" case (worker reconciles silent skips
            // into progress.error, so has_errs catches those too).
            const p = progress[rag_config_id]
            status[rag_config_id] = has_errs
              ? "completed_with_errors"
              : p
                ? calculateStatus(p)
                : "complete"
          } else {
            // failed / cancelled
            status[rag_config_id] = "completed_with_errors"
          }
        }
      }

      return {
        ...state,
        progress,
        logs,
        status,
        running_rag_configs: running,
      }
    })
  }
}

jobs.subscribe(reflect_jobs_into_rag_store)

// derived store that gets project state by project ID and initializes state if does not exist yet
export function getProjectRagStateStore(project_id: string) {
  return derived(ragProgressStore, ($store) => {
    return $store[project_id] || getDefaultProjectState()
  })
}

function createRagProgressStore() {
  const { subscribe, set, update } = writable<
    Record<string, RagConfigurationProgressState>
  >({})

  function getProjectState(project_id: string): RagConfigurationProgressState {
    const state = get(ragProgressStore)
    return state[project_id] || getDefaultProjectState()
  }

  function updateProjectState(
    project_id: string,
    updater: (
      state: RagConfigurationProgressState,
    ) => RagConfigurationProgressState,
  ) {
    update((globalState) => ({
      ...globalState,
      [project_id]: updater(
        globalState[project_id] || getDefaultProjectState(),
      ),
    }))
  }

  function has_errors(rag_config_id: string, project_id: string): boolean {
    const projectState = getProjectState(project_id)
    const progress = projectState.progress[rag_config_id]
    if (!progress) {
      return false
    }
    return (
      (progress.total_document_extracted_error_count ?? 0) > 0 ||
      (progress.total_document_chunked_error_count ?? 0) > 0 ||
      (progress.total_document_embedded_error_count ?? 0) > 0 ||
      (progress.total_chunks_indexed_error_count ?? 0) > 0
    )
  }

  async function run_all_rag_configs(project_id: string): Promise<void> {
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

    // we don't want to throw an error in this side effect as it is supposed to be
    // relatively invisible to the user
    if (error) {
      console.error("Error fetching rag configs", error)
      return
    }

    const tasks: Promise<unknown>[] = data.map((rag_config) => {
      if (!rag_config.id || rag_config.is_archived) {
        return Promise.resolve()
      }
      return run_rag_config(project_id, rag_config.id)
    })

    await Promise.allSettled(tasks)
  }

  async function run_rag_config(
    project_id: string,
    rag_config_id: string,
  ): Promise<void> {
    // Optimistic UI: flip to "running" immediately so the row + global
    // progress indicator update before the spawn round-trip returns.
    updateProjectState(project_id, (state) => ({
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

    progress_ui_state.set({
      title: "Processing Documents",
      body: "",
      link: `/docs/rag_configs/${project_id}`,
      cta: "View Progress",
      progress: 0,
      step_count: null,
      current_step: 0,
    })

    // The new endpoint returns immediately with a `kiln_job_tracking_id`. We
    // then watch the project-scoped jobs store for that specific job — the
    // worker stamps a full RagProgress snapshot under `metadata.rag_progress`
    // on every tick, which is what the existing four-bar dialog reads. Drops
    // the per-RAG SSE plumbing entirely.
    const run_url = `${base_url}/api/projects/${project_id}/rag_configs/${rag_config_id}/run`
    let job_id: string
    try {
      const response = await fetch(run_url)
      if (!response.ok) {
        const text = await response.text()
        throw new Error(
          `Failed to start RAG run: ${response.status} ${text || response.statusText}`,
        )
      }
      const data = (await response.json()) as { kiln_job_tracking_id: string }
      job_id = data.kiln_job_tracking_id
    } catch (err) {
      console.error(
        `Error starting RAG config ${rag_config_id}: ${String(err)}`,
      )
      updateProjectState(project_id, (state) => ({
        ...state,
        logs: {
          ...state.logs,
          [rag_config_id]: [
            ...(state.logs[rag_config_id] ?? []),
            {
              level: "error",
              message: `Error running RAG config: ${String(err)}`,
            },
          ],
        },
      }))
      finalize_run(project_id, rag_config_id, "completed_with_errors")
      return
    }

    await watch_rag_job(project_id, rag_config_id, job_id)
  }

  // Subscribe to the jobs store and pipe the tracked job's RagProgress
  // snapshots into our per-config state. Resolves when the job reaches a
  // terminal status, vanishes from the store (superseded / deleted by the
  // registry), or the subscription is torn down.
  function watch_rag_job(
    project_id: string,
    rag_config_id: string,
    job_id: string,
  ): Promise<void> {
    return new Promise<void>((resolve) => {
      let saw_job = false
      const unsubscribe = jobs.subscribe(($jobs: JobRecord[]) => {
        const job = $jobs.find((j) => j.id === job_id)
        if (!job) {
          // The job was either pruned out from under us (supersede / clear)
          // or hasn't been observed by the jobs SSE stream yet. Only finalize
          // on disappearance — not on a still-empty pre-load — so we don't
          // racefully resolve before the first event lands.
          if (saw_job) {
            unsubscribe()
            finalize_run(
              project_id,
              rag_config_id,
              has_errors(rag_config_id, project_id)
                ? "completed_with_errors"
                : "complete",
            )
            resolve()
          }
          return
        }
        saw_job = true

        const rag_progress = (
          job.metadata as { rag_progress?: RagProgress } | null
        )?.rag_progress
        if (rag_progress) {
          updateProjectState(project_id, (state) => ({
            ...state,
            progress: {
              ...state.progress,
              [rag_config_id]: rag_progress,
            },
            // The worker accumulates logs across ticks and stamps the full
            // list into rag_progress.logs, so we replace (not append) here.
            // No risk of duplicates on every tick — same input → same output.
            logs: {
              ...state.logs,
              [rag_config_id]: rag_progress.logs ?? [],
            },
          }))

          if (
            getProjectState(project_id).last_started_rag_config_id ===
            rag_config_id
          ) {
            progress_ui_state.set({
              title: "Processing Documents",
              body: "",
              link: `/docs/rag_configs/${project_id}`,
              cta: "View Progress",
              progress:
                compute_overall_completion_percentage(rag_progress) / 100,
              step_count: null,
              current_step: null,
            })
          }
        }

        if (is_terminal(job.status)) {
          unsubscribe()
          const status: RagConfigurationStatus =
            job.status === "succeeded" && !has_errors(rag_config_id, project_id)
              ? "complete"
              : "completed_with_errors"
          finalize_run(project_id, rag_config_id, status)
          resolve()
        }
      })
    })
  }

  function finalize_run(
    project_id: string,
    rag_config_id: string,
    status: RagConfigurationStatus,
  ): void {
    updateProjectState(project_id, (state) => ({
      ...state,
      running_rag_configs: {
        ...state.running_rag_configs,
        [rag_config_id]: false,
      },
      status: { ...state.status, [rag_config_id]: status },
    }))
    if (
      getProjectState(project_id).last_started_rag_config_id === rag_config_id
    ) {
      progress_ui_state.set({
        title: "Processing Documents",
        body:
          status === "completed_with_errors"
            ? "Completed with errors"
            : "Completed",
        link: `/docs/rag_configs/${project_id}`,
        cta:
          status === "completed_with_errors" ? "View Errors" : "View Results",
        progress: 1,
        step_count: null,
        current_step: 0,
      })
    }
  }

  return {
    subscribe,
    set,
    update,
    updateProjectState,
    run_all_rag_configs,
    run_rag_config,
    getProjectState,
  }
}

export function sortRagConfigs(
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
        ragProgressStore.updateProjectState(projectId, (projectState) => {
          const newProgress = {
            ...projectState.progress,
            [rag_config_id]: {
              ...projectState.progress[rag_config_id],
              ...progress,
            },
          }

          // we need to make sure not to overwrite the client-side status, otherwise we will
          // lose the progress state when navigating out and back into the pages that
          const newStatus = {
            ...projectState.status,
            [rag_config_id]:
              projectState.status[rag_config_id] ||
              calculateStatus(newProgress[rag_config_id]),
          }

          return {
            ...projectState,
            progress: newProgress,
            status: newStatus,
          }
        })
      }
    }
  } catch (e) {
    ragProgressStore.updateProjectState(projectId, (projectState) => ({
      ...projectState,
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
    ragProgressStore.updateProjectState(project_id, (projectState) => {
      const newRagConfigs = {
        ...projectState.rag_configs,
        ...rag_configs_response.reduce(
          (acc, rag_config) => {
            acc[String(rag_config.id)] = rag_config
            return acc
          },
          {} as Record<string, RagConfigWithSubConfigs>,
        ),
      }
      const newIsArchived = {
        ...projectState.is_archived,
        ...rag_configs_response.reduce(
          (acc, rag_config) => {
            acc[String(rag_config.id)] = rag_config.is_archived
            return acc
          },
          {} as Record<string, boolean>,
        ),
      }
      return {
        ...projectState,
        rag_configs: newRagConfigs,
        is_archived: newIsArchived,
      }
    })
  } catch (e) {
    ragProgressStore.updateProjectState(project_id, (projectState) => ({
      ...projectState,
      error: createKilnError(e),
    }))
  }
}

export async function update_rag_config_archived_state(
  project_id: string,
  rag_config_id: string,
  is_archived: boolean,
) {
  ragProgressStore.updateProjectState(project_id, (projectState) => ({
    ...projectState,
    is_archived: {
      ...projectState.is_archived,
      [rag_config_id]: is_archived,
    },
  }))
}

export function compute_overall_completion_percentage(
  rag_progress: RagProgress,
) {
  if (!rag_progress || rag_progress.total_document_count === 0) {
    return 0
  }

  if (
    rag_progress.total_document_completed_count ===
      rag_progress.total_document_count &&
    rag_progress.total_chunk_completed_count === rag_progress.total_chunk_count
  ) {
    return 100
  }

  const extraction_completion_percentage =
    (rag_progress.total_document_extracted_count +
      rag_progress.total_document_extracted_error_count) /
    (rag_progress.total_document_count || 1)
  const chunking_completion_percentage =
    (rag_progress.total_document_chunked_count +
      rag_progress.total_document_chunked_error_count) /
    (rag_progress.total_document_count || 1)
  const embedding_completion_percentage =
    (rag_progress.total_document_embedded_count +
      rag_progress.total_document_embedded_error_count) /
    (rag_progress.total_document_count || 1)
  const indexing_completion_percentage =
    (rag_progress.total_chunks_indexed_count +
      rag_progress.total_chunks_indexed_error_count) /
    (rag_progress?.total_chunk_count || 1)

  // arbitrary weights, but roughly based on how long each step takes
  const overall_completion_percentage =
    0.75 * extraction_completion_percentage +
    0.1 * chunking_completion_percentage +
    0.1 * embedding_completion_percentage +
    0.05 * indexing_completion_percentage

  return Math.floor(overall_completion_percentage * 100)
}
