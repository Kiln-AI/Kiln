<script lang="ts">
  import AvailableModelsDropdown from "$lib/ui/run_config_component/available_models_dropdown.svelte"
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import { ui_state } from "$lib/stores"
  import { createEventDispatcher } from "svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  export let id: string
  export let task_id: string
  export let pairs_per_part: number = 5
  export let guidance: string = ""

  const dispatch = createEventDispatcher()

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
      const modal = document.getElementById(id)
      // @ts-expect-error dialog is not a standard element
      modal?.close()
    } finally {
      generating = false
    }
  }
</script>

<dialog {id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold">Generate Q&A Pairs</h3>
    <p class="text-sm font-light mb-8">
      Generate question and answer pairs from extracted document content.
    </p>

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

        <!-- Part size moved to extraction modal -->

        <div>
          <label class="label" for="guidance_textarea_modal">
            <span class="label-text font-medium">Guidance</span>
          </label>
          <textarea
            id="guidance_textarea_modal"
            class="textarea textarea-bordered w-full h-64 font-mono text-xs"
            bind:value={guidance}
          />
          <div class="text-xs text-gray-500 mt-1">
            Instructions for the AI on how to generate Q&A pairs
          </div>
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

        <button class="btn btn-primary mt-6" on:click={generate_qa_pairs}>
          Generate Q&A Pairs
        </button>
      </div>
    {/if}
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
