<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { createEventDispatcher, onDestroy, onMount } from "svelte"
  import type { ExtractorConfig } from "$lib/types"
  import { get_model_friendly_name, provider_name_from_id } from "$lib/stores"
  import { extractor_output_format } from "$lib/utils/formatters"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { page } from "$app/stores"
  import { base_url, client } from "$lib/api_client"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import CreateExtractorDialog from "../../../../docs/rag_configs/[project_id]/create_rag_config/create_extractor_dialog.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let selected_extractor_id: string | null = null

  let extractor_configs: ExtractorConfig[] = []
  let extractor_config_error: KilnError | null = null
  let loading_extractor_configs: boolean = true

  const dispatch = createEventDispatcher<{
    extractor_config_selected: { extractor_config_id: string }
    extraction_complete: { extractor_config_id: string }
    close: void
  }>()

  let extracting = false
  let es: EventSource | null = null
  $: project_id = $page.params.project_id

  let extraction_progress = 0
  let extraction_total = 0
  let extraction_errors = 0

  let create_extractor_dialog: Dialog | null = null

  onMount(async () => {
    await loadExtractorConfigs()
  })

  onDestroy(() => {
    es?.close()
    es = null
  })

  async function handle_create_extractor_success(
    event: CustomEvent<{ extractor_config_id: string }>,
  ) {
    create_extractor_dialog?.close()
    await loadExtractorConfigs()
    selected_extractor_id = event.detail.extractor_config_id
  }

  function extractor_label(extractor: ExtractorConfig) {
    return `${get_model_friendly_name(extractor.model_name)} (${provider_name_from_id(extractor.model_provider_name)}) - ${extractor_output_format(extractor.output_format)}`
  }

  async function loadExtractorConfigs() {
    try {
      loading_extractor_configs = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/extractor_configs",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (fetch_error) {
        throw fetch_error
      }

      extractor_configs = data || []
    } catch (e) {
      extractor_config_error = createKilnError(e)
    } finally {
      loading_extractor_configs = false
    }
  }

  $: extractor_options = loading_extractor_configs
    ? []
    : ([
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
      ] as OptionGroup[])

  async function run_extraction() {
    extracting = true
    extractor_config_error = null
    extraction_progress = 0
    extraction_total = 0
    extraction_errors = 0

    try {
      if (!selected_extractor_id || selected_extractor_id === "create_new") {
        throw new Error("Please select an extractor")
      }

      const url = `${base_url}/api/projects/${project_id}/${"extractor_configs"}/${selected_extractor_id}/run_extractor_config`
      // ensure only one live stream - we do not block the user while extraction is running, but we don't want the user to somehow
      // trigger parallel conflicting extraction runs
      es?.close()
      es = new EventSource(url)

      es.onmessage = (event: MessageEvent) => {
        console.info("Extraction message", event.data)
        // server sends progress JSON and a final "complete" message
        if (event.data === "complete") {
          es?.close()
          es = null
          extracting = false

          // should not happen, but typecheck doesn't know
          if (!selected_extractor_id) {
            return
          }

          // Dispatch event
          dispatch("extraction_complete", {
            extractor_config_id: selected_extractor_id,
          })

          // Close modal
          dialog?.close()
        } else {
          try {
            const progress_data = JSON.parse(event.data)
            if (progress_data.progress !== undefined) {
              extraction_progress = progress_data.progress
            }
            if (progress_data.total !== undefined) {
              extraction_total = progress_data.total
            }
            if (progress_data.errors !== undefined) {
              extraction_errors = progress_data.errors
            }
          } catch (parse_error) {
            console.warn("Failed to parse progress data", parse_error)
          }
        }
      }

      es.onerror = (e) => {
        console.error("Extraction stream error", e)
        es?.close()
        es = null
        extractor_config_error = createKilnError(e)
        extracting = false
      }
    } catch (e) {
      extractor_config_error = createKilnError(e)
      es?.close()
      es = null
      extracting = false
    }
  }

  // Trigger create new extractor dialog
  $: if (selected_extractor_id === "create_new") {
    dispatch("extractor_config_selected", { extractor_config_id: "create_new" })
    create_extractor_dialog?.show()
  }
</script>

<Dialog bind:this={dialog} title="Run Extraction" width="normal">
  <FormContainer
    submit_visible={!extracting}
    submit_label="Run Extraction"
    gap={4}
    {keyboard_submit}
    bind:error={extractor_config_error}
    bind:submitting={extracting}
    on:submit={async (_) => {
      await run_extraction()
    }}
    on:close={() => {
      es?.close()
      es = null
      extractor_config_error = null
      extracting = false
      dispatch("close")
    }}
  >
    {#if extracting}
      <div class="min-h-[200px] flex flex-col justify-center items-center">
        <div class="loading loading-spinner loading-lg mb-6 text-success"></div>
        {#if extraction_total > 0}
          <progress
            class="progress w-56 progress-success"
            value={extraction_progress}
            max={extraction_total}
          ></progress>
          <div class="font-light text-xs text-center mt-1">
            {extraction_progress} of {extraction_total} extracted
          </div>
          {#if extraction_errors > 0}
            <div class="text-error font-light text-sm mt-4">
              {extraction_errors} error(s) occurred during extraction
            </div>
          {/if}
        {/if}
      </div>
    {:else if loading_extractor_configs}
      <div class="flex flex-row justify-center">
        <div class="loading loading-spinner loading-lg my-12"></div>
      </div>
    {:else}
      <div class="flex flex-col gap-6">
        <FormElement
          id="extractor_selector_modal"
          label="Extractor"
          description="Extractors convert your documents into text."
          info_description="Documents like PDFs, images and videos need to be converted into text so they can be searched and read by models."
          inputType="fancy_select"
          fancy_select_options={extractor_options}
          bind:value={selected_extractor_id}
          error_message={extractor_config_error?.message}
        />
      </div>
    {/if}
  </FormContainer>
</Dialog>

<CreateExtractorDialog
  bind:dialog={create_extractor_dialog}
  keyboard_submit={true}
  on:success={handle_create_extractor_success}
  on:close={() => {
    create_extractor_dialog?.close()
    extractor_config_error = null
    if (selected_extractor_id === "create_new") {
      selected_extractor_id = null
    }
  }}
/>
