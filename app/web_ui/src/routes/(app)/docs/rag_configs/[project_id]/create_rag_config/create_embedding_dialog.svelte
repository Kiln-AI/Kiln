<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateEmbeddingForm from "./create_embedding_form.svelte"
  import { load_available_embedding_models } from "$lib/stores"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { embedding_config_id: string }
    close: void
  }>()

  onMount(async () => {
    await load_available_embedding_models()
  })
</script>

<Dialog
  bind:this={dialog}
  title="Embedding Configuration"
  subtitle="Convert text chunks into vectors for similarity search."
  width="wide"
  on:close={() => {
    dispatch("close")
  }}
>
  <CreateEmbeddingForm
    {keyboard_submit}
    on:success={(e) => {
      dispatch("success", { embedding_config_id: e.detail.embedding_config_id })
    }}
  />
</Dialog>
