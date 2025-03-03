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
  export let requires_logprobs: boolean = false
  export let error_message: string | null = null
  $: $ui_state.selected_model = model
  $: model_options = format_model_options(
    $available_models || {},
    requires_structured_output,
    requires_data_gen,
    requires_logprobs,
    $ui_state.current_task_id,
  )

  // Export the parsed model name and provider name
  export let model_name: string | null = null
  export let provider_name: string | null = null
  $: get_model_provider(model)
  function get_model_provider(model_provider: string) {
    model_name = model_provider
      ? model_provider.split("/").slice(1).join("/")
      : null
    provider_name = model_provider ? model_provider.split("/")[0] : null
  }

  onMount(async () => {
    await load_available_models()
  })

  let unsupported_models: [string, string][] = []
  let untested_models: [string, string][] = []
  function format_model_options(
    providers: AvailableModels[],
    structured_output: boolean,
    requires_data_gen: boolean,
    requires_logprobs: boolean,
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
        if (requires_logprobs && !model.supports_logprobs) {
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
      let not_recommended_label = "Not Recommended"
      if (requires_data_gen) {
        not_recommended_label = "Not Recommended - Data Gen Not Supported"
      } else if (requires_structured_output) {
        not_recommended_label = "Not Recommended - Structured Output Fails"
      } else if (requires_logprobs) {
        not_recommended_label = "Not Recommended - Logprobs Not Supported"
      }
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
    {:else if requires_logprobs}
      <Warning
        warning_message="This model does not support logprobs. It will likely fail when running a G-eval or other logprob queries."
      />
    {:else if requires_structured_output}
      <Warning
        warning_message="This model is not recommended for use with tasks requiring structured output. It fails to consistently return structured data."
      />
    {/if}
  {/if}
</div>
