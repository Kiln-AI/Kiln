<script lang="ts">
  // The "meat" of the extraction dialog, extracted so it can be embedded inline
  // (e.g. at the bottom of the document select / upload dialogs) as well as
  // inside the standalone extraction_dialog. Renders the extractor selector +
  // "create new" flow + progress UI, and exposes an awaitable run_extraction().
  import FormElement from "$lib/utils/form_element.svelte"
  import { createEventDispatcher, onDestroy, onMount } from "svelte"
  import type { ExtractorConfig } from "$lib/types"
  import { get_model_friendly_name, provider_name_from_id } from "$lib/stores"
  import { extractor_output_format } from "$lib/utils/formatters"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { page } from "$app/stores"
  import { base_url, client } from "$lib/api_client"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateExtractorDialog from "../../routes/(app)/docs/rag_configs/[project_id]/create_rag_config/create_extractor_dialog.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"

  // Tags scoping the extraction run — only documents carrying these tags are
  // extracted. Documents already extracted with the chosen extractor are skipped.
  export let target_tags: string[] = []
  // Document-id allow-list scoping the run. When set, only these documents are
  // extracted (combined with target_tags). Lets a caller extract specific docs
  // without having to tag them. Empty = no id filter.
  export let target_document_ids: string[] = []
  export let selected_extractor_id: string | null = null
  // When true, default the selector to the most-recently-created (non-archived)
  // extractor so the common case is one click.
  export let preselect_default_extractor: boolean = false
  // Bindable: true while an SSE extraction run is in flight. Hosts read this to
  // hide their own controls during the run.
  export let extracting: boolean = false
  // Bindable: surfaced so a host can show the error alongside its own UI.
  export let error: KilnError | null = null
  // When true, the picker renders its own run button + progress in place. When
  // false, the host drives run_extraction() itself (e.g. via a FormContainer
  // submit).
  export let show_run_button: boolean = false
  // Label for the in-component run button. Hosts can word it for their flow
  // (e.g. "Add 5 docs") instead of the generic "Run Extraction".
  export let run_button_label: string = "Run Extraction"
  // Optional async step run before extraction starts (e.g. add + tag the docs).
  // Only invoked by the in-component run button.
  export let before_run: (() => Promise<void>) | null = null
  // Field label + description. Hosts that already explain extraction can pass a
  // concise, context-specific description (or "" to hide it) to avoid repeating
  // the same "documents → text" message in several places.
  export let label: string = "Extractor"
  export let description: string =
    "Extractors convert your documents into text."

  // Unique so multiple pickers can coexist on a page (e.g. inline + the
  // standalone extraction_dialog) without colliding FormElement ids.
  const field_id = "extractor_selector_" + Math.random().toString(36).slice(2)

  let extractor_configs: ExtractorConfig[] = []
  let loading_extractor_configs: boolean = true
  let es: EventSource | null = null
  let extraction_progress = 0
  let extraction_total = 0
  let extraction_errors = 0
  let create_extractor_dialog: Dialog | null = null
  let running_internal = false

  const dispatch = createEventDispatcher<{
    extractor_config_selected: { extractor_config_id: string }
    extraction_complete: { extractor_config_id: string; error_count: number }
  }>()

  $: project_id = $page.params.project_id!

  onMount(async () => {
    await loadExtractorConfigs()
    if (preselect_default_extractor && !selected_extractor_id) {
      const active = extractor_configs.filter((c) => !c.is_archived && !!c.id)
      const most_recent = [...active].sort((a, b) =>
        (b.created_at || "").localeCompare(a.created_at || ""),
      )[0]
      if (most_recent?.id) {
        selected_extractor_id = most_recent.id
      }
    }
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
      error = createKilnError(e)
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

  $: has_valid_extractor =
    !!selected_extractor_id && selected_extractor_id !== "create_new"

  // Awaitable: resolves when the SSE stream reports "complete", rejects on a
  // stream error or if no extractor is selected. Sets `extracting` for the
  // duration so hosts can react.
  export function run_extraction(): Promise<void> {
    extracting = true
    error = null
    extraction_progress = 0
    extraction_total = 0
    extraction_errors = 0

    return new Promise<void>((resolve, reject) => {
      if (!selected_extractor_id || selected_extractor_id === "create_new") {
        error = new KilnError("Please select an extractor", null)
        extracting = false
        reject(error)
        return
      }

      const extractor_id = selected_extractor_id
      const url = new URL(
        `${base_url}/api/projects/${project_id}/extractor_configs/${extractor_id}/run_extractor_config`,
      )
      if (target_tags.length > 0) {
        url.searchParams.set("tags", target_tags.join(","))
      }
      if (target_document_ids.length > 0) {
        url.searchParams.set("document_ids", target_document_ids.join(","))
      }

      // Ensure only one live stream - we don't want to trigger parallel
      // conflicting extraction runs.
      es?.close()
      es = new EventSource(url)

      es.onmessage = (event: MessageEvent) => {
        // Server sends progress JSON and a final "complete" message.
        if (event.data === "complete") {
          es?.close()
          es = null
          extracting = false
          dispatch("extraction_complete", {
            extractor_config_id: extractor_id,
            error_count: extraction_errors,
          })
          resolve()
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
        error = createKilnError(e)
        extracting = false
        reject(error)
      }
    })
  }

  // Reset state before a host re-shows the picker in a reused dialog.
  export function reset() {
    es?.close()
    es = null
    extracting = false
    error = null
    extraction_progress = 0
    extraction_total = 0
    extraction_errors = 0
  }

  async function handle_internal_run() {
    if (running_internal) return
    running_internal = true
    error = null
    try {
      if (before_run) await before_run()
      await run_extraction()
    } catch (e) {
      if (!error) error = createKilnError(e)
    } finally {
      running_internal = false
    }
  }

  // Trigger create new extractor dialog
  $: if (selected_extractor_id === "create_new") {
    dispatch("extractor_config_selected", { extractor_config_id: "create_new" })
    create_extractor_dialog?.show()
  }
</script>

{#if extracting}
  <div class="min-h-[160px] flex flex-col justify-center items-center">
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
  <div class="flex flex-col gap-4">
    <FormElement
      id={field_id}
      {label}
      {description}
      info_description="Documents with existing extractions for the selected extractor will be skipped."
      inputType="fancy_select"
      fancy_select_options={extractor_options}
      bind:value={selected_extractor_id}
      error_message={error?.message}
    />
    {#if show_run_button}
      <button
        type="button"
        class="btn btn-primary btn-sm h-10 min-w-24 self-end"
        disabled={!has_valid_extractor || running_internal}
        on:click={handle_internal_run}
      >
        {run_button_label}
      </button>
    {/if}
  </div>
{/if}

<CreateExtractorDialog
  bind:dialog={create_extractor_dialog}
  keyboard_submit={true}
  on:success={handle_create_extractor_success}
  on:close={() => {
    create_extractor_dialog?.close()
    error = null
    if (selected_extractor_id === "create_new") {
      selected_extractor_id = null
    }
  }}
/>
