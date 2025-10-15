<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { createEventDispatcher } from "svelte"
  import type { ExtractorConfig } from "$lib/types"
  import { get_model_friendly_name, provider_name_from_id } from "$lib/stores"
  import { extractor_output_format } from "$lib/utils/formatters"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { page } from "$app/stores"
  import { base_url } from "$lib/api_client"

  export let id: string
  export let extractor_configs: ExtractorConfig[] = []
  export let selected_extractor_id: string | null = null
  export let part_size: "small" | "medium" | "large" | "full" = "medium"

  const dispatch = createEventDispatcher()

  let extracting = false
  $: project_id = $page.params.project_id

  function extractor_label(extractor: ExtractorConfig) {
    return `${get_model_friendly_name(extractor.model_name)} (${provider_name_from_id(extractor.model_provider_name)}) - ${extractor_output_format(extractor.output_format)}`
  }

  $: extractor_options = [
    {
      options: [
        {
          label: "New Extractor Configuration",
          value: "create_new",
          badge: "＋",
          badge_color: "primary",
        },
      ],
    },
    ...(extractor_configs.length > 0
      ? [
          {
            label: "Extractors",
            options: extractor_configs
              .filter((config) => !config.is_archived)
              .map((config) => ({
                label: extractor_label(config),
                value: config.id,
                description:
                  config.name +
                  (config.description ? " - " + config.description : ""),
              })),
          },
        ]
      : []),
  ] as OptionGroup[]

  async function run_extraction() {
    if (!selected_extractor_id || selected_extractor_id === "create_new") {
      return
    }

    extracting = true
    try {
      const url = `${base_url}/api/projects/${project_id}/${"extractor_configs"}/${selected_extractor_id}/run_extractor_config`
      const es = new EventSource(url)

      es.onmessage = (event: MessageEvent) => {
        // server sends progress JSON and a final "complete" message
        if (event.data === "complete") {
          es.close()
          extracting = false

          // Dispatch event
          dispatch("extraction_complete", {
            extractor_id: selected_extractor_id,
          })

          // Close modal
          const modal = document.getElementById(id)
          // @ts-expect-error dialog is not a standard element
          modal?.close()
        }
      }

      es.onerror = (e) => {
        console.error("Extraction stream error", e)
        es.close()
        extracting = false
      }
    } catch (e) {
      console.error("Failed to start extraction", e)
      extracting = false
    }
  }

  // Trigger create new extractor dialog
  $: if (selected_extractor_id === "create_new") {
    dispatch("create_extractor")
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
    <h3 class="text-lg font-bold">Run Extraction</h3>
    <p class="text-sm font-light mb-8">
      Extract text content from your selected documents.
    </p>

    {#if extracting}
      <div class="flex flex-row justify-center">
        <div class="loading loading-spinner loading-lg my-12"></div>
      </div>
    {:else}
      <div class="flex flex-col gap-6">
        <FormElement
          id="extractor_selector_modal"
          label="Extractor"
          description="Choose an extractor to extract text from your documents."
          info_description="Extractors process documents and extract their text content. Select one that matches your document types."
          inputType="fancy_select"
          fancy_select_options={extractor_options}
          bind:value={selected_extractor_id}
        />

        <div>
          <label class="label" for="part_size_select_modal">
            <span class="label-text font-medium">Document Part Size</span>
          </label>
          <select
            id="part_size_select_modal"
            class="select select-bordered w-full"
            bind:value={part_size}
          >
            <option value="small">Small (~500 tokens)</option>
            <option value="medium">Medium (~1000 tokens)</option>
            <option value="large">Large (~2000 tokens)</option>
            <option value="full">Full Document (no splitting)</option>
          </select>
          <div class="text-xs text-gray-500 mt-1">
            How to split documents for Q&A generation
          </div>
        </div>

        <button
          class="btn btn-primary mt-6"
          on:click={run_extraction}
          disabled={!selected_extractor_id ||
            selected_extractor_id === "create_new"}
        >
          Run Extraction
        </button>
      </div>
    {/if}
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
