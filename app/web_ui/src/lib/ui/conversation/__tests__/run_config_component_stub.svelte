<script lang="ts">
  // Minimal stub of RunConfigComponent for composer tests.
  // Captures the model/prompt props the composer passes in, and exposes
  // run_options_as_run_config_properties() and friends so the composer
  // can call them as if it were the real component.
  import type { RunConfigProperties, Task } from "$lib/types"

  export let project_id: string
  export let current_task: Task | null = null
  export let model: string | null = null
  export let prompt_method: string = "simple_prompt_builder"
  export let requires_structured_output: boolean = false
  export let show_name_field: boolean = true
  export let selected_run_config_id: string | null = null
  export let set_default_error: unknown = null
  export let selected_model_specific_run_config_id: string | null = null

  // Reference all props so eslint-no-unused-vars does not complain. These
  // are all real props the composer (or real component) passes.
  $: void requires_structured_output
  $: void show_name_field
  $: void selected_run_config_id
  $: void set_default_error
  $: void selected_model_specific_run_config_id

  export function run_options_as_run_config_properties(): RunConfigProperties {
    const provider = (model ?? "openai/gpt-4o").split("/")[0]
    const model_name = (model ?? "openai/gpt-4o").split("/").slice(1).join("/")
    return {
      type: "kiln_agent",
      // @ts-expect-error stub
      model_provider_name: provider,
      model_name: model_name,
      prompt_id: prompt_method,
      temperature: 1,
      top_p: 1,
      structured_output_mode: "default",
      thinking_level: null,
      tools_config: { tools: [] },
    }
  }

  export function get_selected_model(): string | null {
    return model
  }

  export function clear_run_options_errors() {}
  export function clear_model_dropdown_error() {}
  export function set_model_dropdown_error(_: string) {
    void _
  }
  export function get_prompt_method(): string {
    return prompt_method
  }
  export function get_tools(): string[] {
    return []
  }
  export function get_skills(): string[] {
    return []
  }
</script>

<div
  data-testid="run-config-stub"
  data-project-id={project_id}
  data-task-id={current_task?.id ?? ""}
  data-model={model ?? ""}
  data-prompt-method={prompt_method}
></div>
