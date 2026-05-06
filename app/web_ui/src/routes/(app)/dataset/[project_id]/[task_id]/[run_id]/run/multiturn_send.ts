import { client } from "$lib/api_client"
import { isMcpRunConfig, type RunConfigProperties } from "$lib/types"

export type RunConfigController = {
  clear_run_options_errors: () => void
  clear_model_dropdown_error: () => void
  run_options_as_run_config_properties: () => RunConfigProperties
  get_selected_model: () => string | null
  set_model_dropdown_error: (msg: string) => void
}

export type InputFormController = {
  get_plaintext_input_data: () => string | null
  clear_input: () => void
}

export type SendMultiturnArgs = {
  project_id: string
  task_id: string
  parent_task_run_id: string | null | undefined
  run_config_component: RunConfigController | null | undefined
  input_form: InputFormController | null | undefined
  on_success: (new_run_id: string) => Promise<void> | void
  tags?: string[]
}

export type SendMultiturnResult =
  | { ok: true; new_run_id: string }
  | { ok: false; error: unknown }

// Pure-ish, side-effect-light helper that performs the multiturn Send flow.
// On success the caller-provided on_success runs first (so navigation happens),
// and the input form is only cleared after on_success resolves. This way an
// error in on_success does not silently drop the user's typed text.
export async function send_multiturn(
  args: SendMultiturnArgs,
): Promise<SendMultiturnResult> {
  const {
    project_id,
    task_id,
    parent_task_run_id,
    run_config_component,
    input_form,
    on_success,
    tags = ["multiturn_run"],
  } = args

  if (!parent_task_run_id) {
    return {
      ok: false,
      error: new Error(
        "Cannot send a multiturn message: the current run is not loaded yet.",
      ),
    }
  }

  if (!run_config_component) {
    return {
      ok: false,
      error: new Error(
        "Task configuration is still loading. Please wait a moment and try again.",
      ),
    }
  }

  run_config_component.clear_run_options_errors()
  run_config_component.clear_model_dropdown_error()
  const run_config_properties =
    run_config_component.run_options_as_run_config_properties()
  const is_mcp = isMcpRunConfig(run_config_properties)
  if (!is_mcp && !run_config_component.get_selected_model()) {
    run_config_component.set_model_dropdown_error("Required")
    return {
      ok: false,
      error: new Error("You must select a model before sending"),
    }
  }

  const text = input_form?.get_plaintext_input_data() ?? ""
  const { data, error: fetch_error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/run",
    {
      params: { path: { project_id, task_id } },
      body: {
        run_config_properties,
        plaintext_input: text,
        structured_input: null,
        tags,
        parent_task_run_id,
      },
    },
  )

  if (fetch_error) {
    return { ok: false, error: fetch_error }
  }
  if (!data?.id) {
    return {
      ok: false,
      error: new Error("Server did not return a new run id."),
    }
  }

  await on_success(data.id)
  // Only clear input after on_success resolves. If on_success throws, the
  // caller catches it and the textarea contents are preserved.
  input_form?.clear_input()
  return { ok: true, new_run_id: data.id }
}
