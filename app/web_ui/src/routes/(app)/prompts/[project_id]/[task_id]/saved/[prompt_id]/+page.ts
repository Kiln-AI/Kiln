import { load_task_prompts } from "$lib/stores/prompts_store"

export const prerender = false

// Runs on every navigation (including same-route param changes), so the store
// is always fresh when the component reads it — fixes stale-data bug when
// navigating between detail pages for entities created mid-session.
export async function load({
  params,
}: {
  params: { project_id: string; task_id: string }
}) {
  await load_task_prompts(params.project_id, params.task_id, true)
}
