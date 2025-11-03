<script lang="ts">
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import type { RunConfigProperties } from "$lib/types"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import ChunkingConfigForm from "./chunking_config_form.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"

  type GenerateQnAPairsEvent = {
    pairs_per_part: number
    guidance: string
    split_documents_into_chunks: boolean
    chunk_size_tokens: number | null
    chunk_overlap_tokens: number | null
    runConfigProperties: RunConfigProperties
  }

  export let project_id: string
  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let pairs_per_part: number = 5
  export let guidance: string = ""
  export let target_description: string = "all documents"
  export let generation_target_type: "all" | "document" | "part" = "all"

  export let split_documents_into_chunks: boolean = false
  export let chunk_size_tokens: number | null = null
  export let chunk_overlap_tokens: number | null = null

  $: show_chunking_options = generation_target_type === "all"

  let run_config_component: RunConfigComponent | null = null
  let submitting = false
  let error: KilnError | null = null

  const dispatch = createEventDispatcher<{
    generate_requested: GenerateQnAPairsEvent
    close: void
  }>()

  function generate_qa_pairs() {
    try {
      submitting = true
      error = null
      if (!run_config_component) {
        throw new Error("Run config component is not initialized")
      }

      const run_config_properties =
        run_config_component.run_options_as_run_config_properties()
      if (!run_config_properties.model_name) {
        throw new Error("Please select a model to generate Q&A pairs")
      }

      dispatch("generate_requested", {
        pairs_per_part,
        guidance,
        split_documents_into_chunks,
        runConfigProperties:
          run_config_component.run_options_as_run_config_properties(),
        chunk_size_tokens,
        chunk_overlap_tokens,
      })
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title="Generate Q&A Pairs"
  width="wide"
  sub_subtitle={target_description === "all documents"
    ? "All session documents"
    : `Document: ${target_description}`}
>
  <FormContainer
    bind:submitting
    submit_label="Generate Q&A Pairs"
    gap={4}
    {keyboard_submit}
    on:submit={generate_qa_pairs}
    on:close={() => dispatch("close")}
    {error}
  >
    <div class="flex flex-row items-center gap-4 mt-4 mb-2">
      <div class="flex-grow font-medium text-sm">
        Q&A Pairs per {split_documents_into_chunks ? "Chunk" : "Document"}
        <div class="text-xs text-gray-500">
          {`Number of query-answer pairs to generate from each ${
            split_documents_into_chunks ? "chunk" : "document"
          }`}
        </div>
      </div>
      <IncrementUi bind:value={pairs_per_part} />
    </div>
    <div class="flex flex-col gap-6">
      {#if show_chunking_options}
        <ChunkingConfigForm
          bind:split_documents_into_chunks
          bind:chunk_size_tokens
          bind:chunk_overlap_tokens
        />
      {/if}

      <FormElement
        id="guidance_textarea"
        inputType="textarea"
        label="Guidance"
        description="Instructions for the AI on how to generate query-answer pairs"
        bind:value={guidance}
        height="medium"
      />

      <RunConfigComponent
        bind:this={run_config_component}
        {project_id}
        requires_structured_output={true}
        hide_prompt_selector={true}
        hide_tools_selector={true}
        model_dropdown_settings={{
          requires_data_gen: true,
        }}
      />
    </div>
  </FormContainer>
</Dialog>
