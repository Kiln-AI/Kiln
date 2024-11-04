<script lang="ts">
  import {
    available_models,
    load_available_models,
    ui_state,
  } from "$lib/stores"
  import type { AvailableModels } from "$lib/types"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"

  export let model: string = $ui_state.selected_model
  export let requires_structured_output: boolean = false
  export let error_message: string | null = "sdf"
  $: $ui_state.selected_model = model
  $: model_options = format_model_options(
    $available_models || {},
    requires_structured_output,
  )

  onMount(async () => {
    await load_available_models()
  })

  function format_model_options(
    providers: AvailableModels[],
    structured_output: boolean,
  ): [string, [unknown, string][]][] {
    let options = []
    for (const provider of providers) {
      let model_list = []
      for (const model of provider.models) {
        let id = provider.provider_id + "/" + model.id
        if (!structured_output || model.supports_structured_output) {
          model_list.push([id, model.name])
        }
      }
      if (model_list.length > 0) {
        options.push([provider.provider_name, model_list])
      }
    }
    // @ts-expect-error this is the correct format, but TS isn't finding it
    return options
  }

  // Extra check to make sure the model is available to use
  export function get_selected_model(): string | null {
    for (const provider of model_options) {
      if (provider[1].find((m) => m[0] === model)) {
        return model
      }
    }
    return null
  }
</script>

<FormElement
  label="Model"
  bind:value={model}
  info_description={requires_structured_output
    ? "Some models are not available for tasks that require structured output"
    : ""}
  id="model"
  inputType="select"
  bind:error_message
  select_options_grouped={model_options}
/>
