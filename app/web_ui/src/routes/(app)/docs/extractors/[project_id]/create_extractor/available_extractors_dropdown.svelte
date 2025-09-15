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

  export let extractor: string = ""
  export let label: string = "Extractor"
  export let description: string | undefined = undefined
  export let error_message: string | null = null
  export let suggested_mode: "doc_extraction" | null = null

  // Export the parsed extractor type, model name and provider name
  export let extractor_type: "litellm" | "llama_pdf_reader" | null = null
  export let model_name: string | null = null
  export let provider_name: string | null = null

  $: model_options = format_extractor_options(
    $available_models || [],
    $ui_state.current_task_id,
    $recent_model_store,
    $model_info,
  )

  function get_extractor_info(extractor_value: string) {
    if (extractor_value === "llama_pdf_reader") {
      extractor_type = "llama_pdf_reader"
      model_name = null
      provider_name = null
    } else {
      extractor_type = "litellm"
      model_name = extractor_value
        ? extractor_value.split("/").slice(1).join("/")
        : null
      provider_name = extractor_value ? extractor_value.split("/")[0] : null
    }
  }

  $: get_extractor_info(extractor)

  $: addRecentModel(model_name, provider_name)

  onMount(async () => {
    await load_available_models()
    await load_model_info()
  })

  let unsupported_models: Option[] = []
  let untested_models: Option[] = []
  let previous_extractor: string = extractor

  function get_extractor_warning(selected: string): string | null {
    if (unsupported_models.some((m) => m.value === selected)) {
      return "This model is not recommended for document extraction. It may not work as expected."
    }

    return null
  }

  function confirm_extractor_select(event: Event) {
    const select = event.target as HTMLSelectElement
    const selected = select.value
    const warning = get_extractor_warning(selected)
    if (warning && !confirm(warning)) {
      select.value = previous_extractor
      extractor = previous_extractor
      return
    }
    previous_extractor = selected
  }

  function format_extractor_options(
    providers: AvailableModels[],
    current_task_id: string | null,
    recent_models: RecentModel[],
    model_data: ProviderModels | null,
  ): OptionGroup[] {
    let options: OptionGroup[] = []
    unsupported_models = []
    untested_models = []

    // Add llama_pdf_reader as the first option
    options.push({
      label: "Specialized Extractors",
      options: [
        {
          value: "llama_pdf_reader",
          label: "Llama PDF Reader",
          badge: "Recommended",
        },
      ],
    })

    // Recent models section
    let recent_model_list: Option[] = []
    for (const recent_model of recent_models) {
      const model_details = available_model_details(
        recent_model.model_id,
        recent_model.model_provider,
        providers,
      )
      if (!model_details || !model_details.supports_doc_extraction) {
        continue
      }
      recent_model_list.push({
        value: recent_model.model_provider + "/" + recent_model.model_id,
        label:
          model_name_from_id(recent_model.model_id, model_data) +
          " (" +
          provider_name_from_id(recent_model.model_provider) +
          ")",
      })
    }
    if (recent_model_list.length > 0) {
      options.push({
        label: "Recent Models",
        options: recent_model_list,
      })
    }

    // ML Models section
    for (const provider of providers) {
      let model_list: Option[] = []
      for (const model of provider.models) {
        if (!model.supports_doc_extraction) {
          continue
        }
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

        // For now, we don't have unsupported models for doc extraction
        // but we keep the structure for future use
        const unsupported = false
        if (unsupported) {
          unsupported_models.push({
            value: id,
            label: long_label,
          })
          continue
        }

        let badge: string | undefined = undefined
        if (
          suggested_mode === "doc_extraction" &&
          model.suggested_for_doc_extraction
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
      options.push({
        label: "Not Recommended",
        options: unsupported_models,
      })
    }

    return options
  }

  // Extra check to make sure the extractor is available to use
  export function get_selected_extractor(): string | null {
    for (const provider of model_options) {
      if (provider.options.find((m) => m.value === extractor)) {
        return extractor
      }
    }
    return null
  }

  $: selected_extractor_untested = untested_models.find(
    (m) => m.value === extractor,
  )
  $: selected_extractor_unsupported = unsupported_models.find(
    (m) => m.value === extractor,
  )

  $: selected_extractor_suggested_doc_extraction =
    available_model_details(model_name, provider_name, $available_models)
      ?.suggested_for_doc_extraction || false

  $: is_llama_pdf_reader = extractor === "llama_pdf_reader"
</script>

<div>
  <FormElement
    {label}
    {description}
    bind:value={extractor}
    id="extractor"
    inputType="fancy_select"
    on_select={confirm_extractor_select}
    bind:error_message
    fancy_select_options={model_options}
    placeholder="Select an extractor"
  />

  {#if selected_extractor_untested}
    <Warning
      warning_message="This model has not been tested with Kiln. It may not work as expected."
    />
  {:else if selected_extractor_unsupported}
    <Warning
      warning_message="This model is not recommended for document extraction. It may not work as expected."
    />
  {:else if is_llama_pdf_reader}
    <Warning
      warning_icon="check"
      warning_color="success"
      warning_message="Llama PDF Reader is a specialized extractor optimized for PDF documents. It provides high-quality text extraction without requiring an AI model."
    />
  {:else if suggested_mode === "doc_extraction"}
    <Warning
      warning_icon={!extractor
        ? "info"
        : selected_extractor_suggested_doc_extraction
          ? "check"
          : "exclaim"}
      warning_color={!extractor
        ? "gray"
        : selected_extractor_suggested_doc_extraction
          ? "success"
          : "warning"}
      warning_message="For doc extraction, we recommend using a high quality multimodal model like Gemini Pro or the specialized Llama PDF Reader."
    />
  {/if}
</div>
