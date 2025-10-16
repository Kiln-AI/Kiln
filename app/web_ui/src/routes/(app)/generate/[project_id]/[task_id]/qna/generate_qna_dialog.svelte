<script lang="ts">
  import AvailableModelsDropdown from "$lib/ui/run_config_component/available_models_dropdown.svelte"
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import { ui_state } from "$lib/stores"
  import { createEventDispatcher } from "svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let task_id: string
  export let pairs_per_part: number = 5
  export let guidance: string = ""

  const dispatch = createEventDispatcher<{
    generation_complete: {
      pairs_per_part: number
      guidance: string
      model: string
    }
    close: void
  }>()

  let model: string = $ui_state.selected_model
  let generating = false

  async function generate_qa_pairs() {
    generating = true
    try {
      // Emit configuration; page component will perform API call
      dispatch("generation_complete", {
        pairs_per_part,
        guidance,
        model,
      })
      dialog?.close()
    } finally {
      generating = false
    }
  }
</script>

<Dialog bind:this={dialog} title="Generate Q&A Pairs" width="normal">
  <FormContainer
    submit_visible={true}
    submit_label="Generate Q&A Pairs"
    gap={4}
    {keyboard_submit}
    on:submit={async (_) => {
      await generate_qa_pairs()
    }}
    on:close={() => dispatch("close")}
  >
    {#if generating}
      <div class="flex flex-row justify-center">
        <div class="loading loading-spinner loading-lg my-12"></div>
      </div>
    {:else}
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
          bind:model
        />

        <!-- Part size moved to extraction modal -->
        <FormElement
          id="guidance_textarea_modal"
          inputType="textarea"
          label="Guidance"
          description="Instructions for the AI on how to generate Q&A pairs"
          bind:value={guidance}
          height="large"
        />
      </div>
    {/if}
  </FormContainer>
</Dialog>
