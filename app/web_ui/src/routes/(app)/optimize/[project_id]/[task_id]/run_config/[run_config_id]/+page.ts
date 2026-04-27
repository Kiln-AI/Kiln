import { load_task_prompts } from "$lib/stores/prompts_store"
import { load_task_run_configs } from "$lib/stores/run_configs_store"

export const prerender = false

// Runs on every navigation (including same-route param changes), so the stores
// are always fresh when the component reads them — fixes stale-data bug when
// navigating between detail pages for entities created mid-session.
export async function load({
  params,
}: {
  params: { project_id: string; task_id: string }
}) {
  await Promise.all([
    load_task_run_configs(params.project_id, params.task_id, true),
    load_task_prompts(params.project_id, params.task_id, true),
  ])
}
