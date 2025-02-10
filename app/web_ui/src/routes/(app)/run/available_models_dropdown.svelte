<script lang="ts">
  import {
    available_models,
    load_available_models,
    ui_state,
  } from "$lib/stores"
  import type { AvailableModels } from "$lib/types"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"

  export let model: string = $ui_state.selected_model
  export let requires_structured_output: boolean = false
  export let requires_data_gen: boolean = false
  export let error_message: string | null = null
  $: $ui_state.selected_model = model
  $: model_options = format_model_options(
    $available_models || {},
    requires_structured_output,
    requires_data_gen,
    $ui_state.current_task_id,
  )

  onMount(async () => {
    await load_available_models()
  })

  let unsupported_models: [string, string][] = []
  let untested_models: [string, string][] = []
  function format_model_options(
    providers: AvailableModels[],
    structured_output: boolean,
    requires_data_gen: boolean,
    current_task_id: string | null,
  ): [string, [unknown, string][]][] {
    let options = []
    unsupported_models = []
    untested_models = []
    for (const provider of providers) {
      let model_list = []
      for (const model of provider.models) {
        // Exclude models that are not available for the current task
        if (
          model &&
          model.task_filter &&
          current_task_id &&
          !model.task_filter.includes(current_task_id)
        ) {
          continue
        }

        let id = provider.provider_id + "/" + model.id
        let long_label = provider.provider_name + " / " + model.name
        if (model.untested_model) {
          untested_models.push([id, long_label])
          continue
        }
        if (requires_data_gen && !model.supports_data_gen) {
          unsupported_models.push([id, long_label])
          continue
        }
        if (structured_output && !model.supports_structured_output) {
          unsupported_models.push([id, long_label])
          continue
        }
        model_list.push([id, model.name])
      }
      if (model_list.length > 0) {
        options.push([provider.provider_name, model_list])
      }
    }

    if (untested_models.length > 0) {
      options.push(["Untested Models", untested_models])
    }

    if (unsupported_models.length > 0) {
      const not_recommended_label = requires_data_gen
        ? "Not Recommended - Data Gen Not Supported"
        : "Not Recommended - Structured Output Fails"
      options.push([not_recommended_label, unsupported_models])
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

  $: selected_model_untested = untested_models.find((m) => m[0] === model)
  $: selected_model_unsupported = unsupported_models.find((m) => m[0] === model)
</script>

<div>
  <FormElement
    label="Model"
    bind:value={model}
    id="model"
    inputType="select"
    bind:error_message
    select_options_grouped={model_options}
  />

  {#if selected_model_untested}
    <Warning
      warning_message="This model has not been tested with Kiln. It may not work as expected."
    />
  {:else if selected_model_unsupported}
    {#if requires_data_gen}
      <Warning
        warning_message="This model is not recommended for use with data generation. It's known to generate incorrect data."
      />
    {:else if requires_structured_output}
      <Warning
        warning_message="This model is not recommended for use with tasks requiring structured output. It fails to consistently return structured data."
      />
    {/if}
  {/if}
</div>
