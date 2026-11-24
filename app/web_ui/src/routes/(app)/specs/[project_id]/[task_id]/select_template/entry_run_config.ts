import type { TaskRunConfig } from "$lib/types"
import { lookup_run_openenv_server } from "$lib/api/openenv_server_api"

// The run config "Write My Eval" goes ahead with when the task has saved ones:
// the task default, else the most recently created. Null when the task has
// none, so the page asks instead. A default id that no longer matches a saved
// config (deleted since) is skipped.
export function pick_entry_run_config(
  run_configs: TaskRunConfig[],
  default_run_config_id: string | null | undefined,
): TaskRunConfig | null {
  const by_id = (id: string | null | undefined) =>
    id ? run_configs.find((rc) => rc.id === id) ?? null : null
  return (
    by_id(default_run_config_id) ??
    [...run_configs].sort((a, b) =>
      (b.created_at ?? "").localeCompare(a.created_at ?? ""),
    )[0] ??
    null
  )
}

// The name of the OpenEnv server a run with these tools starts on, or null
// when the tools reach none. The tools decide the server, so the entry page
// shows it rather than asking for it. A lookup that fails also gives null:
// the name is shown for context, and the builder checks the server itself.
export async function run_config_world_name(
  project_id: string,
  task_id: string,
  tool_ids: string[],
): Promise<string | null> {
  if (tool_ids.length === 0) return null
  try {
    const result = await lookup_run_openenv_server(
      project_id,
      task_id,
      tool_ids,
    )
    return result.openenv_server?.name ?? null
  } catch (e) {
    console.warn("Could not look up the run config's OpenEnv server:", e)
    return null
  }
}
