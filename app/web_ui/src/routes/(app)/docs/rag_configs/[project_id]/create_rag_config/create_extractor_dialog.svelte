<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateExtractorForm from "../../../extractors/[project_id]/create_extractor/create_extractor_form.svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { extractor_config_id: string }
    close: void
  }>()
</script>

<Dialog
  bind:this={dialog}
  title="Extractor Configuration"
  subtitle="Extractors convert your documents into text."
  width="wide"
  on:close={() => {
    dispatch("close")
  }}
>
  <CreateExtractorForm
    {keyboard_submit}
    on:success={(e) => {
      dispatch("success", { extractor_config_id: e.detail.extractor_config_id })
    }}
  />
</Dialog>
