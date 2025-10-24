<script lang="ts">
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import { createEventDispatcher } from "svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import type { RunConfigProperties } from "$lib/types"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import ChunkingConfigForm from "./chunking_config_form.svelte"

  export let project_id: string
  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let pairs_per_part: number = 5
  export let guidance: string = ""
  export let target_description: string = "all documents"
  export let generation_target_type: "all" | "document" | "part" = "all"

  export let use_full_documents: boolean = true
  export let chunk_size_tokens: number | null = null
  export let chunk_overlap_tokens: number | null = null

  $: show_chunking_options = generation_target_type === "all"

  let run_config_component: RunConfigComponent | null = null

  const dispatch = createEventDispatcher<{
    generate_requested: {
      pairs_per_part: number
      guidance: string
      chunk_size_tokens: number | null
      chunk_overlap_tokens: number | null
      runConfigProperties: RunConfigProperties
    }
    close: void
  }>()

  let submitting = false
  function generate_qa_pairs() {
    if (!run_config_component) {
      throw new Error("Run config component is not initialized")
    }

    dispatch("generate_requested", {
      pairs_per_part,
      guidance,
      runConfigProperties:
        run_config_component.run_options_as_run_config_properties(),
      chunk_size_tokens,
      chunk_overlap_tokens,
    })

    submitting = false
  }
</script>

<Dialog
  bind:this={dialog}
  title="Generate Q&A Pairs"
  width="wide"
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
    <div class="flex flex-col gap-4">
      {#if show_chunking_options}
        <div class="pt-4">
          <ChunkingConfigForm
            bind:use_full_documents
            bind:chunk_size_tokens
            bind:chunk_overlap_tokens
          />
        </div>
      {/if}

      <div class="flex flex-row items-center gap-4">
        <div class="flex-grow text-sm">
          Q&A Pairs per {use_full_documents ? "Document" : "Part"}
          <InfoTooltip
            tooltip_text={`Number of question-answer pairs to generate from each ${use_full_documents ? "document" : "part"}`}
          />
        </div>
        <IncrementUi bind:value={pairs_per_part} />
      </div>

      <div class="border-t pt-4">
        <FormElement
          id="guidance_textarea_modal"
          inputType="textarea"
          label="Guidance"
          description="Instructions for the AI on how to generate Q&A pairs"
          bind:value={guidance}
          height="medium"
        />
      </div>

      <div class="border-t pt-4">
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
    </div>
  </FormContainer>
</Dialog>
