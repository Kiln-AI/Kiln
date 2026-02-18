import type { RunConfigProperties, TaskRunConfig } from "$lib/types"
import { isMcpRunConfig } from "$lib/types"

export function is_mcp_run_config(
  config: TaskRunConfig | null | undefined,
): boolean {
  return isMcpRunConfig(config?.run_config_properties)
}

export function is_mcp_run_config_properties(
  props: RunConfigProperties | null | undefined,
): boolean {
  return isMcpRunConfig(props)
}
