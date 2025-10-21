<script lang="ts">
  import AvailableModelsDropdown from "$lib/ui/run_config_component/available_models_dropdown.svelte"
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import { createEventDispatcher } from "svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { number_validator } from "$lib/utils/input_validators"

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

  $: show_chunking_options = generation_target_type === "all"

  const dispatch = createEventDispatcher<{
    generation_complete: {
      pairs_per_part: number
      guidance: string
      model: string
      chunk_size_tokens: number | null
      chunk_overlap_tokens: number | null
    }
    close: void
  }>()

  let selected_model: string
  let submitting = false
  function generate_qa_pairs() {
    if (!selected_model) {
      throw new Error("Model is required")
    }

    dispatch("generation_complete", {
      pairs_per_part,
      guidance,
      model: selected_model,
      chunk_size_tokens,
      chunk_overlap_tokens,
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
    </div>
  </FormContainer>
</Dialog>
