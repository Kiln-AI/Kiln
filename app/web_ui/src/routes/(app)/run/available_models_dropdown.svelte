<script lang="ts">
  import {
    available_models,
    load_available_models,
    available_model_details,
    ui_state,
    provider_name_from_id,
    model_name as model_name_from_id,
    model_info,
    load_model_info,
  } from "$lib/stores"
  import {
    addRecentModel,
    type RecentModel,
    recent_model_store,
  } from "$lib/stores/recent_model_store"
  import type { AvailableModels, ProviderModels } from "$lib/types"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"

  const LOGPROBS_WARNING =
    "This model does not support logprobs. It will likely fail when running a G-eval or other logprob queries."

  export let model: string = $ui_state.selected_model
  export let requires_structured_output: boolean = false
  export let requires_data_gen: boolean = false
  export let requires_logprobs: boolean = false
  export let requires_uncensored_data_gen: boolean = false
  export let error_message: string | null = null
  export let suggested_mode:
    | "data_gen"
    | "evals"
    | "uncensored_data_gen"
    | null = null
  $: $ui_state.selected_model = model
  $: model_options = format_model_options(
    $available_models || {},
    requires_structured_output,
    requires_data_gen,
    requires_uncensored_data_gen,
    requires_logprobs,
    $ui_state.current_task_id,
    $recent_model_store,
    $model_info,
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

  $: addRecentModel(model_name, provider_name)

  onMount(async () => {
    await load_available_models()
    await load_model_info()
  })

  let unsupported_models: Option[] = []
  let untested_models: Option[] = []
  let previous_model: string = model

  function get_model_warning(selected: string): string | null {
    if (
      unsupported_models.some((m) => m.value === selected && requires_logprobs)
    ) {
      return LOGPROBS_WARNING
    }

    return null
  }

  function confirm_model_select(event: Event) {
    const select = event.target as HTMLSelectElement
    const selected = select.value
    const warning = get_model_warning(selected)
    if (warning && !confirm(warning)) {
      select.value = previous_model
      model = previous_model
      return
    }
    previous_model = selected
  }

  function format_model_options(
    providers: AvailableModels[],
    structured_output: boolean,
    requires_data_gen: boolean,
    requires_uncensored_data_gen: boolean,
    requires_logprobs: boolean,
    current_task_id: string | null,
    recent_models: RecentModel[],
    model_data: ProviderModels | null,
  ): OptionGroup[] {
    let options: OptionGroup[] = []
    unsupported_models = []
    untested_models = []

    // Recent models section
    if (recent_models.length > 0) {
      let recent_model_list: Option[] = []
      for (const recent_model of recent_models) {
        recent_model_list.push({
          value: recent_model.model_provider + "/" + recent_model.model_id,
          label:
            model_name_from_id(recent_model.model_id, model_data) +
            " (" +
            provider_name_from_id(recent_model.model_provider) +
            ")",
        })
      }
      options.push({
        label: "Recent Models",
        options: recent_model_list,
      })
    }

    for (const provider of providers) {
      let model_list: Option[] = []
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
          untested_models.push({
            value: id,
            label: long_label,
          })
          continue
        }

        const unsupported =
          (requires_data_gen && !model.supports_data_gen) ||
          (structured_output && !model.supports_structured_output) ||
          (requires_logprobs && !model.supports_logprobs) ||
          (requires_uncensored_data_gen && !model.uncensored)
        if (unsupported) {
          unsupported_models.push({
            value: id,
            label: long_label,
          })
          continue
        }

        let badge: string | undefined = undefined
        if (
          (suggested_mode === "data_gen" && model.suggested_for_data_gen) ||
          (suggested_mode === "evals" && model.suggested_for_evals) ||
          (suggested_mode === "uncensored_data_gen" &&
            model.suggested_for_uncensored_data_gen)
        ) {
          badge = "Recommended"
        }
        model_list.push({
          value: id,
          label: model.name,
          badge: badge,
        })
      }
      if (model_list.length > 0) {
        options.push({
          label: provider.provider_name,
          options: model_list,
        })
      }
    }

    if (untested_models.length > 0) {
      options.push({
        label: "Untested Models",
        options: untested_models,
      })
    }

    if (unsupported_models.length > 0) {
      let not_recommended_label = "Not Recommended"
      if (requires_uncensored_data_gen) {
        not_recommended_label =
          "Not Recommended - Uncensored Data Gen Not Supported"
      } else if (requires_data_gen) {
        not_recommended_label = "Not Recommended - Data Gen Not Supported"
      } else if (requires_structured_output) {
        not_recommended_label = "Not Recommended - Structured Output Fails"
      } else if (requires_logprobs) {
        not_recommended_label = "Not Recommended - Logprobs Not Supported"
      }

      options.push({
        label: not_recommended_label,
        options: unsupported_models,
      })
    }

    return options
  }

  // Extra check to make sure the model is available to use
  export function get_selected_model(): string | null {
    for (const provider of model_options) {
      if (provider.options.find((m) => m.value === model)) {
        return model
      }
    }
    return null
  }

  $: selected_model_untested = untested_models.find((m) => m.value === model)
  $: selected_model_unsupported = unsupported_models.find(
    (m) => m.value === model,
  )

  $: selected_model_suggested_data_gen =
    available_model_details(model_name, provider_name, $available_models)
      ?.suggested_for_data_gen || false

  $: selected_model_suggested_uncensored_data_gen =
    available_model_details(model_name, provider_name, $available_models)
      ?.suggested_for_uncensored_data_gen || false

  $: selected_model_suggested_evals =
    available_model_details(model_name, provider_name, $available_models)
      ?.suggested_for_evals || false
</script>

<div>
  <FormElement
    label="Model"
    bind:value={model}
    id="model"
    inputType="fancy_select"
    on_select={confirm_model_select}
    bind:error_message
    fancy_select_options={model_options}
    placeholder="Select a model"
  />

  {#if selected_model_untested}
    <Warning
      warning_message="This model has not been tested with Kiln. It may not work as expected."
    />
  {:else if selected_model_unsupported}
    {#if requires_uncensored_data_gen}
      <Warning
        warning_message="This model is not recommended for the current data gen template. It will refuse to follow instructions for sensitive topics."
      />
    {:else if requires_data_gen}
      <Warning
        warning_message="This model is not recommended for use with data generation. It's known to generate incorrect data."
      />
    {:else if requires_logprobs}
      <Warning large_icon warning_message={LOGPROBS_WARNING} />
    {:else if requires_structured_output}
      <Warning
        warning_message="This model is not recommended for use with tasks requiring structured output. It fails to consistently return structured data."
      />
    {/if}
  {:else if suggested_mode === "data_gen"}
    <Warning
      warning_icon={!model
        ? "info"
        : selected_model_suggested_data_gen
          ? "check"
          : "exclaim"}
      warning_color={!model
        ? "gray"
        : selected_model_suggested_data_gen
          ? "success"
          : "warning"}
      warning_message="For data gen we suggest using a high quality model such as GPT 4.1, Sonnet, Gemini Pro or R1."
    />
  {:else if suggested_mode === "uncensored_data_gen"}
    <Warning
      warning_icon={!model
        ? "info"
        : selected_model_suggested_uncensored_data_gen
          ? "check"
          : "exclaim"}
      warning_color={!model
        ? "gray"
        : selected_model_suggested_uncensored_data_gen
          ? "success"
          : "warning"}
      warning_message="For this data gen template we suggest a large uncensored model like Grok 3."
    />
  {:else if suggested_mode === "evals"}
    <Warning
      warning_icon={!model
        ? "info"
        : selected_model_suggested_evals
          ? "check"
          : "exclaim"}
      warning_color={!model
        ? "gray"
        : selected_model_suggested_evals
          ? "success"
          : "warning"}
      warning_message="For evals we suggest using a high quality model such as GPT 4.1, Sonnet, Gemini Pro or R1."
    />
  {/if}
</div>
