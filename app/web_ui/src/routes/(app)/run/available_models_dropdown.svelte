<script lang="ts">
  import {
    available_models,
    load_available_models,
    available_model_details,
    ui_state,
    recently_used_models,
    add_recently_used_model,
  } from "$lib/stores"
  import type { AvailableModels } from "$lib/types"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"

  export let model: string | null = $ui_state.selected_model
  export let requires_structured_output: boolean = false
  export let requires_data_gen: boolean = false
  export let requires_logprobs: boolean = false
  export let error_message: string | null = null
  export let suggested_mode: "data_gen" | "evals" | null = null

  // Track previous task ID to detect changes
  let previous_task_id: string | null = null
  $: {
    if ($ui_state.current_task_id !== previous_task_id) {
      model = null
      ui_state.update((state) => ({ ...state, selected_model: null }))
      previous_task_id = $ui_state.current_task_id
    }
  }

  $: model_options = format_model_options(
    $available_models || {},
    requires_structured_output,
    requires_data_gen,
    requires_logprobs,
    $ui_state.current_task_id,
    $ui_state.current_project_id,
    $recently_used_models,
  )

  // Export the parsed model name and provider name
  export let model_name: string | null = null
  export let provider_name: string | null = null
  $: get_model_provider(model)
  function get_model_provider(model_provider: string | null) {
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
    current_project_id: string | null,
    recent_models: Record<string, string[]>,
  ): [string, [string, string][]][] {
    let options: [string, [string, string][]][] = []
    unsupported_models = []
    untested_models = []

    // Add recently used models section if there are any
    const key =
      current_project_id && current_task_id
        ? `${current_project_id}/${current_task_id}`
        : null
    const task_recent_models = key ? recent_models[key] || [] : []
    if (task_recent_models.length > 0) {
      const recent_model_list: [string, string][] = []
      for (const model_id of task_recent_models) {
        const [provider_id, model_name] = model_id.split("/")
        // Find the model details
        for (const provider of providers) {
          if (provider.provider_id === provider_id) {
            const model = provider.models.find(
              (m: { id: string }) => m.id === model_name,
            )
            if (model) {
              // Check if model meets requirements
              if (
                (requires_data_gen && !model.supports_data_gen) ||
                (structured_output && !model.supports_structured_output) ||
                (requires_logprobs && !model.supports_logprobs)
              ) {
                continue
              }
              recent_model_list.push([
                model_id,
                provider.provider_name + " / " + model.name,
              ])
              break
            }
          }
        }
      }
      if (recent_model_list.length > 0) {
        options.push(["Recently Used", recent_model_list])
      }
    }

    // Add regular model sections
    for (const provider of providers) {
      let model_list: [string, string][] = []
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
        let model_name = model.name
        if (suggested_mode === "data_gen" && model.suggested_for_data_gen) {
          model_name = model.name + "  —  Recommended"
        } else if (suggested_mode === "evals" && model.suggested_for_evals) {
          model_name = model.name + "  —  Recommended"
        }
        model_list.push([id, model_name])
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

  $: selected_model_suggested_data_gen =
    available_model_details(model_name, provider_name, $available_models)
      ?.suggested_for_data_gen || false

  $: selected_model_suggested_evals =
    available_model_details(model_name, provider_name, $available_models)
      ?.suggested_for_evals || false

  // Add model to recently used when selected
  $: if (model) {
    add_recently_used_model(model)
  }
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
