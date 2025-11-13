<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateChunkerForm from "./create_chunker_form.svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { chunker_config_id: string }
    close: void
  }>()
</script>

<Dialog
  bind:this={dialog}
  title="Chunker Configuration"
  subtitle="Split document text into smaller chunks for search."
  width="wide"
  on:close={() => {
    dispatch("close")
  }}
>
  <CreateChunkerForm
    {keyboard_submit}
    on:success={(e) => {
      dispatch("success", { chunker_config_id: e.detail.chunker_config_id })
    }}
  />
</Dialog>
