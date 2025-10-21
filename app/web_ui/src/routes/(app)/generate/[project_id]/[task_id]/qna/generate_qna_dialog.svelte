<script lang="ts">
  import AvailableModelsDropdown from "$lib/ui/run_config_component/available_models_dropdown.svelte"
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import { createEventDispatcher } from "svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { number_validator } from "$lib/utils/input_validators"
  import Collapse from "$lib/ui/collapse.svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let task_id: string
  export let pairs_per_part: number = 5
  export let guidance: string = ""
  export let target_description: string = "all documents"
  export let generation_target_type: "all" | "document" | "part" = "all"

  export let use_full_documents: boolean = true
  export let chunk_size_tokens: number | null = null
  export let chunk_overlap_tokens: number | null = null

  let temperature: number = 1.0
  let top_p: number = 1.0

  $: show_chunking_options = generation_target_type === "all"

  const dispatch = createEventDispatcher<{
    generate_requested: {
      pairs_per_part: number
      guidance: string
      model: string
      chunk_size_tokens: number | null
      chunk_overlap_tokens: number | null
      temperature: number
      top_p: number
    }
    close: void
  }>()

  function validate_temperature(value: unknown): string | null {
    if (typeof value === "string") {
      if (value.trim() === "") {
        return "Value is required"
      }
      const numValue = parseFloat(value)
      if (isNaN(numValue)) {
        return "Please enter a valid number"
      }
      value = numValue
    }
    if (typeof value !== "number") {
      return "Please enter a valid number"
    }
    if (value < 0) {
      return "Temperature must be at least 0"
    }
    if (value > 2) {
      return "Temperature must be at most 2"
    }
    return null
  }

  function validate_top_p(value: unknown): string | null {
    if (typeof value === "string") {
      if (value.trim() === "") {
        return "Value is required"
      }
      const numValue = parseFloat(value)
      if (isNaN(numValue)) {
        return "Please enter a valid number"
      }
      value = numValue
    }
    if (typeof value !== "number") {
      return "Please enter a valid number"
    }
    if (value < 0) {
      return "Top P must be at least 0"
    }
    if (value > 1) {
      return "Top P must be at most 1"
    }
    return null
  }

  let selected_model: string
  let submitting = false
  function generate_qa_pairs() {
    if (!selected_model) {
      throw new Error("Model is required")
    }

    dispatch("generate_requested", {
      pairs_per_part,
      guidance,
      model: selected_model,
      chunk_size_tokens,
      chunk_overlap_tokens,
      temperature,
      top_p,
    })

    // We need this to prevent the button from staying in loading state forever
    submitting = false
  }

  $: {
    if (use_full_documents) {
      chunk_size_tokens = null
      chunk_overlap_tokens = null
    } else {
      chunk_size_tokens = 8192
      chunk_overlap_tokens = 256
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title="Generate Q&A Pairs"
  width="normal"
  subtitle={target_description === "all documents"
    ? "All Documents"
    : `Document: ${target_description}`}
>
  <FormContainer
    bind:submitting
    submit_label="Generate Q&A Pairs"
    gap={4}
    {keyboard_submit}
    on:submit={generate_qa_pairs}
    on:close={() => dispatch("close")}
  >
    <div class="flex flex-col gap-6">
      <div class="flex flex-row items-center gap-4 mt-4 mb-2">
        <div class="flex-grow font-medium text-sm">
          Q&A Pairs per Document Part
          <InfoTooltip
            tooltip_text="Number of question-answer pairs to generate from each document section"
          />
        </div>
        <IncrementUi bind:value={pairs_per_part} />
      </div>

      <AvailableModelsDropdown
        {task_id}
        settings={{
          requires_data_gen: true,
          requires_uncensored_data_gen: false,
          suggested_mode: "data_gen",
        }}
        bind:model={selected_model}
      />

      {#if show_chunking_options}
        <FormElement
          id="use_full_documents_checkbox"
          inputType="checkbox"
          label="Use entire documents without splitting into parts"
          description="Generate Q&A using whole documents."
          info_description="For very long documents such as books, manuals, transcripts, splitting up the documents into smaller parts helps create more focused Q&A pairs."
          bind:value={use_full_documents}
        />

        {#if !use_full_documents}
          <div class="space-y-2">
            <FormElement
              id="chunk_size_tokens"
              inputType="input_number"
              label="Part size (tokens)"
              description="The approximate number of words to include in each chunk."
              info_description="Smaller chunks allow for more granular search, but may not encapsulate the broader context."
              bind:value={chunk_size_tokens}
              disabled={use_full_documents}
              validator={(value) =>
                use_full_documents
                  ? null
                  : number_validator({
                      min: 1,
                      integer: true,
                      label: "Document Part Size",
                      optional: false,
                    })(value)}
            />
            <FormElement
              id="chunk_overlap_tokens"
              inputType="input_number"
              label="Part Overlap"
              description="The number of words to overlap between chunks."
              info_description="Without overlap, sentences that span chunk boundaries can be lost because they aren't fully contained in any chunk."
              bind:value={chunk_overlap_tokens}
              disabled={use_full_documents}
              validator={(value) =>
                use_full_documents
                  ? null
                  : number_validator({
                      min: 0,
                      max: chunk_size_tokens || undefined,
                      integer: true,
                      label: "Document Part Overlap",
                      optional: false,
                    })(value)}
            />
          </div>
        {/if}
      {/if}

      <FormElement
        id="guidance_textarea_modal"
        inputType="textarea"
        label="Guidance"
        description="Instructions for the AI on how to generate Q&A pairs"
        bind:value={guidance}
        height="large"
      />

      <Collapse title="Advanced">
        <FormElement
          id="temperature"
          label="Temperature"
          inputType="input"
          info_description="A value from 0.0 to 2.0.\nTemperature is a parameter that controls the randomness of the model's output.\nLower values make the output more focused and deterministic, while higher values make it more creative and varied."
          bind:value={temperature}
          validator={validate_temperature}
        />

        <FormElement
          id="top_p"
          label="Top P"
          inputType="input"
          info_description="A value from 0.0 to 1.0.\nTop P is a parameter that controls the diversity of the model's output.\nLower values make the output more focused and deterministic, while higher values make it more creative and varied."
          bind:value={top_p}
          validator={validate_top_p}
        />
      </Collapse>
    </div>
  </FormContainer>
</Dialog>
