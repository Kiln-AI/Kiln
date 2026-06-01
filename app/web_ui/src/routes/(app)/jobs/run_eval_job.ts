import type { EvalConfig, TaskRunConfig } from "$lib/types"
import type { OptionGroup } from "$lib/ui/fancy_select_types"
import { formatEvalConfigName } from "$lib/utils/formatters"
import { getRunConfigModelDisplayName } from "$lib/utils/run_config_formatters"
import type { ProviderModels } from "$lib/types"
import type { create_eval_job } from "$lib/stores/job_creators"
import type { client } from "$lib/api_client"

export type RunEvalSelection = {
  project_id: string | null
  task_id: string | null
  eval_id: string | null
  eval_config_id: string | null
  run_config_id: string | null
}

export type RunEvalJobParams = {
  project_id: string
  task_id: string
  eval_id: string
  eval_config_id: string
  run_config_id: string
}

// All four picks (plus a current task) are required before a job can start.
export function can_submit_run_eval(selection: RunEvalSelection): boolean {
  return build_run_eval_params(selection) !== null
}

// Returns the create_job param payload when the selection is complete, else null.
export function build_run_eval_params(
  selection: RunEvalSelection,
): RunEvalJobParams | null {
  const { project_id, task_id, eval_id, eval_config_id, run_config_id } =
    selection
  if (
    !project_id ||
    !task_id ||
    !eval_id ||
    !eval_config_id ||
    !run_config_id
  ) {
    return null
  }
  return { project_id, task_id, eval_id, eval_config_id, run_config_id }
}

// Starts the eval background job for a complete selection. Returns true if a
// job was started; false when the selection is incomplete (nothing to do).
export async function start_eval_job(
  create_eval_job_fn: typeof create_eval_job,
  selection: RunEvalSelection,
): Promise<boolean> {
  const params = build_run_eval_params(selection)
  if (!params) {
    return false
  }
  await create_eval_job_fn(params)
  return true
}

// Default judge first (badged), matching the compare_run_configs picker.
export function eval_config_options(
  configs: EvalConfig[] | null,
  default_eval_config_id: string | null | undefined,
  model_info: ProviderModels | null,
): OptionGroup[] {
  if (!configs || configs.length === 0) {
    return []
  }
  const sorted = [...configs].sort((a, b) => {
    if (a.id === default_eval_config_id) return -1
    if (b.id === default_eval_config_id) return 1
    return 0
  })
  return [
    {
      label: "Judges",
      options: sorted.map((config) => ({
        value: config.id,
        label: formatEvalConfigName(config, model_info),
        badge: config.id === default_eval_config_id ? "Default" : undefined,
      })),
    },
  ]
}

// Resolved judge state for an eval, or STALE when the request was superseded.
export type LoadEvalJudgesResult =
  | {
      stale: false
      eval_configs: EvalConfig[]
      default_eval_config_id: string | null
      selected_eval_config_id: string | null
    }
  | { stale: true }

const STALE: LoadEvalJudgesResult = { stale: true }

// Loads an eval's default judge and its judge list. `is_current` is checked
// after every await so a superseded request (the user switched evals while the
// GETs were in flight) bails out instead of clobbering newer state.
export async function load_eval_judges(
  get: typeof client.GET,
  params: { project_id: string; task_id: string; eval_id: string },
  is_current: () => boolean,
): Promise<LoadEvalJudgesResult> {
  const { project_id, task_id, eval_id } = params

  const evaluator_resp = await get(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
    { params: { path: { project_id, task_id, eval_id } } },
  )
  if (!is_current()) {
    return STALE
  }
  if (evaluator_resp.error) {
    throw evaluator_resp.error
  }
  const default_eval_config_id = evaluator_resp.data.current_config_id ?? null

  const configs_resp = await get(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_configs",
    { params: { path: { project_id, task_id, eval_id } } },
  )
  if (!is_current()) {
    return STALE
  }
  if (configs_resp.error) {
    throw configs_resp.error
  }
  const eval_configs = configs_resp.data
  const selected_eval_config_id =
    default_eval_config_id ?? eval_configs[0]?.id ?? null

  return {
    stale: false,
    eval_configs,
    default_eval_config_id,
    selected_eval_config_id,
  }
}

// Default run config first (badged), then alphabetical — mirrors the eval table.
export function run_config_options(
  configs: TaskRunConfig[] | null,
  default_run_config_id: string | null | undefined,
  model_info: ProviderModels | null,
): OptionGroup[] {
  if (!configs || configs.length === 0) {
    return []
  }
  const sorted = [...configs].sort((a, b) => {
    if (a.id === default_run_config_id) return -1
    if (b.id === default_run_config_id) return 1
    return a.name.localeCompare(b.name)
  })
  return [
    {
      label: "Run Methods",
      options: sorted.map((config) => {
        const model_name = getRunConfigModelDisplayName(config, model_info)
        return {
          value: config.id,
          label: model_name ? `${config.name} — ${model_name}` : config.name,
          badge: config.id === default_run_config_id ? "Default" : undefined,
        }
      }),
    },
  ]
}
