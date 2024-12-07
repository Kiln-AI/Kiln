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

  {#if selected_model_unsupported || selected_model_untested}
    <div class="text-sm text-gray-500 flex flex-row items-center mt-2">
      <svg
        class="w-5 h-5 text-error flex-none"
        fill="currentColor"
        width="800px"
        height="800px"
        viewBox="0 0 256 256"
        id="Flat"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
        />
      </svg>

      <div class="pl-4">
        {#if selected_model_untested}
          This model has not been tested with Kiln. It may not work as expected.
        {:else if selected_model_unsupported}
          This model is not recommended
          {#if requires_data_gen}
            for use with data generation. It's known to generate incorrect data.
          {:else if requires_structured_output}
            for use with tasks requiring structured output. It fails to
            consistently return structured data.
          {/if}
        {/if}
      </div>
    </div>
  {/if}
</div>
