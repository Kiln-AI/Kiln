import type { TaskRunConfig } from "$lib/types"
import type { RunConfigProperties } from "$lib/types"

export function is_mcp_run_config(
  config: TaskRunConfig | null | undefined,
): boolean {
  return config?.run_config_properties?.kind === "mcp"
}

export function is_mcp_run_config_properties(
  props: RunConfigProperties | null | undefined,
): boolean {
  return props?.kind === "mcp"
}
