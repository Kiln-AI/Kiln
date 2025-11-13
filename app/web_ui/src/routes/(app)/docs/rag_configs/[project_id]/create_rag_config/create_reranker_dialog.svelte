<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateRerankerForm from "./create_reranker_form.svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { reranker_config_id: string }
    close: void
  }>()
</script>

<Dialog
  bind:this={dialog}
  title="Reranker Configuration"
  subtitle="Choose how to rerank the search results."
  width="wide"
  on:close={() => {
    dispatch("close")
  }}
>
  <CreateRerankerForm
    {keyboard_submit}
    on:success={async (e) => {
      dispatch("success", {
        reranker_config_id: e.detail.reranker_config_id,
      })
    }}
  />
</Dialog>
