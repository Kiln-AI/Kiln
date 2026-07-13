<script lang="ts">
  // Shared generation-settings config for the input data guide setup + refine
  // flows. Renders no inline UI of its own — the parent renders its own trigger
  // (a gear card / link) and calls open_combined_dialog() to launch the settings
  // dialog. Parents read the resulting config via get_input_run_config().
  import { onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import {
    available_models,
    load_available_models,
    model_info,
    load_model_info,
    model_name as friendly_model_name,
    provider_name_from_id,
  } from "$lib/stores"
  import type { AvailableModels, RunConfigProperties } from "$lib/types"

  export let project_id: string
  // Bindable friendly names for the currently-selected input model, so the
  // parent can render its own trigger (e.g. "GPT-5.5" / "OpenRouter").
  export let selected_model_name_display: string = ""
  export let selected_provider_display: string = ""

  let combined_config_dialog: Dialog
  let input_run_config_component: RunConfigComponent | null = null
  let input_model_name: string = ""
  let input_provider: string = ""

  function pick_data_gen_model(providers: AvailableModels[]): string | null {
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

  // Initial recommended model. Without this RunConfigComponent falls back to
  // ui_state.selected_model (the user's last pick anywhere in the app), which
  // is not what we want for an SDG defaulted page.
  let recommended_data_gen_model: string | null = null
  $: if (!recommended_data_gen_model && $available_models.length > 0) {
    recommended_data_gen_model = pick_data_gen_model($available_models)
  }

  // `input_model_name` is the model id, `input_provider` the provider id — both
  // kept in sync by RunConfigComponent. Resolve each to a friendly name.
  $: selected_model_name_display = input_model_name
    ? friendly_model_name(input_model_name, $model_info)
    : ""
  $: selected_provider_display = input_provider
    ? provider_name_from_id(input_provider)
    : ""

  onMount(() => {
    load_available_models()
    load_model_info()
  })

  // Optional custom primary action for the settings dialog's footer, set per
  // open. Defaults to a plain "Done" (just close). Callers that want the dialog
  // to advance a flow (e.g. "Continue" into a review) pass an action here.
  type CombinedAction = { label: string; action: () => boolean }
  let combined_action_override: CombinedAction | null = null

  export function open_combined_dialog(action: CombinedAction | null = null) {
    combined_action_override = action
    combined_config_dialog?.show()
  }

  export function get_input_run_config(): RunConfigProperties | null {
    return (
      input_run_config_component?.run_options_as_run_config_properties() ?? null
    )
  }
</script>

<Dialog
  bind:this={combined_config_dialog}
  title="Generation Settings"
  sub_subtitle="The run options used to generate synthetic inputs for review."
  action_buttons={combined_action_override
    ? [
        {
          label: combined_action_override.label,
          action: combined_action_override.action,
          isPrimary: true,
        },
      ]
    : [{ label: "Done", isPrimary: true }]}
>
  <RunConfigComponent
    bind:this={input_run_config_component}
    bind:model_name={input_model_name}
    bind:provider={input_provider}
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
