<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import ExtractorPicker from "./extractor_picker.svelte"
  import { KilnError } from "$lib/utils/error_handlers"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let selected_extractor_id: string | null = null
  export let target_tags: string[] = []
  // Optional document-id allow-list, forwarded to the extractor picker. Lets a
  // caller scope the run to specific documents without tagging them.
  export let target_document_ids: string[] = []
  // When true, default the selector to the most-recently-created (non-archived)
  // extractor so the common case is one click. Off by default to leave other
  // callers' behavior unchanged.
  export let preselect_default_extractor: boolean = false
  // Bindable: true while an SSE extraction run is in flight. Hosts read this to
  // reflect progress in their own UI (e.g. a spinner on their Continue button)
  // after the user dismisses this dialog mid-run.
  export let extracting = false

  const dispatch = createEventDispatcher<{
    extractor_config_selected: { extractor_config_id: string }
    extraction_complete: { extractor_config_id: string; error_count: number }
    extraction_failed: { error: KilnError | null }
    close: void
  }>()

  let picker: ExtractorPicker
  let error: KilnError | null = null

  function handle_complete(
    event: CustomEvent<{ extractor_config_id: string; error_count: number }>,
  ) {
    dispatch("extraction_complete", event.detail)
    dialog?.close()
  }
</script>

<Dialog
  bind:this={dialog}
  title="Document Extraction"
  sub_subtitle="Documents like PDFs, images and videos need to be converted into text before they can be used as example inputs."
  width="normal"
  on:close={() => {
    // Native close (X / Esc / backdrop). Don't reset while a run is live — that
    // would close the EventSource and cancel the extraction. The user can
    // dismiss this dialog and the run keeps going, still firing
    // extraction_complete. Hosts listen to `close` to release their own
    // controls when the user abandons before running.
    if (!extracting) {
      picker?.reset()
      error = null
    }
    dispatch("close")
  }}
>
  <FormContainer
    submit_visible={!extracting}
    submit_label="Run Extraction"
    gap={4}
    {keyboard_submit}
    bind:error
    bind:submitting={extracting}
    on:submit={async () => {
      try {
        await picker.run_extraction()
      } catch {
        // Also surfaced inline via the bound `error`; forward so a host can
        // mirror it (e.g. on its Continue button) after this dialog closes.
        dispatch("extraction_failed", { error })
      }
    }}
  >
    <ExtractorPicker
      bind:this={picker}
      bind:extracting
      bind:error
      bind:selected_extractor_id
      {target_tags}
      {target_document_ids}
      {preselect_default_extractor}
      show_run_button={false}
      on:extractor_config_selected={(e) =>
        dispatch("extractor_config_selected", e.detail)}
      on:extraction_complete={handle_complete}
    />
  </FormContainer>
</Dialog>
