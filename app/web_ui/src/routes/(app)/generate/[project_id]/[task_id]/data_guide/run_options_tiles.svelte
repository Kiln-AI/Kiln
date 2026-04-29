<script lang="ts">
  // Shared "Generation Options" block for the data guide setup + refine flows.
  // Renders two clickable tiles (one per stage) inside an outlined Collapse,
  // each opening a dialog with the full RunConfigComponent.
  //
  // Parents read the resulting configs via the exposed
  // get_input_run_config() / get_output_run_config() methods.
  import { onMount } from "svelte"
  import type { Task, KilnAgentRunConfigProperties } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import { client } from "$lib/api_client"
  import {
    available_models,
    load_available_models,
    model_info,
    load_model_info,
    model_name as friendly_model_name,
  } from "$lib/stores"
  import type { AvailableModels, RunConfigProperties } from "$lib/types"

  type SDGRecommendedModel = { provider_id: string; model_id: string }

  export let project_id: string
  // Optional — used by the output dialog to mirror the SDG output flow
  // (prompt + tools/skills at top level, requires_structured_output keyed off
  // task.output_json_schema). Falls back to safe defaults if absent.
  export let task: Task | null = null

  let input_config_dialog: Dialog
  let output_config_dialog: Dialog
  let input_run_config_component: RunConfigComponent | null = null
  let output_run_config_component: RunConfigComponent | null = null
  // Bound from each RunConfigComponent so the tile labels stay in sync with the
  // user's selection (and pick up the auto-selected default model on first
  // mount).
  let input_model_name: string = ""
  let output_model_name: string = ""

  // Priority list of (provider, model) pairs, sourced from the remote model
  // config (`sdg_recommended_models` key) via the backend. The first entry
  // whose provider is configured + model exists in available_models becomes
  // the auto-selected default. Falls back to scanning available_models for
  // any provider flagged as suggested_for_data_gen if the API returns nothing.
  let sdg_recommended: SDGRecommendedModel[] = []

  function pick_first_available(
    recommendations: SDGRecommendedModel[],
    providers: AvailableModels[],
  ): string | null {
    for (const rec of recommendations) {
      const provider = providers.find((p) => p.provider_id === rec.provider_id)
      if (!provider) continue
      const model = provider.models.find(
        (m) =>
          m.id === rec.model_id &&
          !m.deprecated &&
          !m.untested_model &&
          m.supports_data_gen &&
          m.supports_structured_output,
      )
      if (model) {
        return `${provider.provider_id}/${model.id}`
      }
    }
    return null
  }

  function pick_fallback_data_gen_model(
    providers: AvailableModels[],
  ): string | null {
    for (const provider of providers) {
      for (const m of provider.models) {
        if (
          m.suggested_for_data_gen &&
          m.supports_structured_output &&
          m.supports_data_gen &&
          !m.deprecated &&
          !m.untested_model
        ) {
          return `${provider.provider_id}/${m.id}`
        }
      }
    }
    return null
  }

  // Initial recommended model passed into both RunConfigComponents. Without
  // this RunConfigComponent falls back to ui_state.selected_model (the user's
  // last pick anywhere in the app), which is not what we want for an SDG
  // defaulted page. Computed once available_models + sdg_recommended load.
  let recommended_data_gen_model: string | null = null
  $: if (!recommended_data_gen_model && $available_models.length > 0) {
    const fromList = pick_first_available(sdg_recommended, $available_models)
    recommended_data_gen_model =
      fromList ?? pick_fallback_data_gen_model($available_models)
  }

  onMount(async () => {
    load_available_models()
    load_model_info()
    try {
      const { data } = await client.GET("/api/sdg_recommended_models")
      if (data) {
        sdg_recommended = data
      }
    } catch {
      // Non-critical — fall back to scanning available_models.
    }
  })

  function open_input_config_dialog() {
    input_config_dialog?.show()
  }

  function open_output_config_dialog() {
    output_config_dialog?.show()
  }

  export function get_input_run_config(): RunConfigProperties | null {
    return (
      input_run_config_component?.run_options_as_run_config_properties() ?? null
    )
  }

  export function get_output_run_config(): RunConfigProperties | null {
    return (
      output_run_config_component?.run_options_as_run_config_properties() ??
      null
    )
  }
</script>

<Collapse title="Generation Options" outlined={true}>
  <div class="text-sm text-gray-500">
    Choose the models used to test your data guide. Defaults to a recommended
    model — click to customize other run options.
  </div>
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <button
      type="button"
      class="text-left rounded-lg border p-4 hover:border-primary hover:shadow-sm transition-all"
      on:click={open_input_config_dialog}
    >
      <div class="text-xs text-gray-500 uppercase font-medium">
        Input Generation
      </div>
      <div class="mt-1 truncate">
        {input_model_name
          ? friendly_model_name(input_model_name, $model_info)
          : "Select model"}
      </div>
    </button>
    <button
      type="button"
      class="text-left rounded-lg border p-4 hover:border-primary hover:shadow-sm transition-all"
      on:click={open_output_config_dialog}
    >
      <div class="text-xs text-gray-500 uppercase font-medium">
        Output Generation
      </div>
      <div class="mt-1 truncate">
        {output_model_name
          ? friendly_model_name(output_model_name, $model_info)
          : "Select model"}
      </div>
    </button>
  </div>
</Collapse>

<!-- Input Generation Run Config Dialog -->
<Dialog
  bind:this={input_config_dialog}
  title="Input Generation Run Options"
  sub_subtitle="Configure the model used to generate example inputs."
  action_buttons={[{ label: "Done", isPrimary: true }]}
>
  <RunConfigComponent
    bind:this={input_run_config_component}
    bind:model_name={input_model_name}
    model={recommended_data_gen_model}
    {project_id}
    requires_structured_output={true}
    show_name_field={false}
    hide_prompt_selector={true}
    show_tools_selector_in_advanced={true}
    model_dropdown_settings={{
      requires_data_gen: true,
      suggested_mode: "data_gen",
    }}
  />
</Dialog>

<!-- Output Generation Run Config Dialog -->
<!-- Mirrors the SDG output flow: prompt + tools/skills selectors stay at top
     level (not collapsed into Advanced), and structured-output requirement
     keys off the task's own output schema. -->
<Dialog
  bind:this={output_config_dialog}
  title="Output Generation Run Options"
  sub_subtitle="Configure the model used to generate example outputs."
  action_buttons={[{ label: "Done", isPrimary: true }]}
>
  <RunConfigComponent
    bind:this={output_run_config_component}
    bind:model_name={output_model_name}
    model={recommended_data_gen_model}
    {project_id}
    current_task={task}
    requires_structured_output={!!task?.output_json_schema}
    show_name_field={false}
    model_dropdown_settings={{
      requires_structured_output: !!task?.output_json_schema,
      requires_data_gen: true,
      suggested_mode: "data_gen",
    }}
  />
</Dialog>
