import type { components } from "$lib/api_schema"
import { isMcpRunConfig, type RunConfigProperties } from "$lib/types"
import type { ResetKwargs } from "$lib/utils/openenv"

export type RunTaskRequest = components["schemas"]["RunTaskRequest"]

export type RunRequestArgs = {
  run_config_properties: RunConfigProperties
  plaintext_input: string | null
  structured_input: RunTaskRequest["structured_input"]
  // The saved run config the options came from, or null for custom options.
  task_run_config_id: string | null
  get_openenv_reset_kwargs: () => Promise<ResetKwargs | null>
}

/** The body of the run page's single-turn POST /run. */
export async function build_run_request(
  args: RunRequestArgs,
): Promise<RunTaskRequest> {
  // MCP run configs call one tool directly and never reach an OpenEnv.
  const openenv_reset_kwargs = isMcpRunConfig(args.run_config_properties)
    ? null
    : await args.get_openenv_reset_kwargs()
  return {
    run_config_properties: args.run_config_properties,
    plaintext_input: args.plaintext_input,
    structured_input: args.structured_input,
    tags: ["manual_run"],
    task_run_config_id: args.task_run_config_id,
    ...(openenv_reset_kwargs ? { openenv_reset_kwargs } : {}),
  }
}
