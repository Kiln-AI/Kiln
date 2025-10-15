<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateVectorStoreForm from "./create_vector_store_form.svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { vector_store_config_id: string }
    close: void
  }>()
</script>

<Dialog
  bind:this={dialog}
  title="Search Index Configuration"
  subtitle="Choose how documents will be indexed and searched."
  width="wide"
  on:close={() => {
    dispatch("close")
  }}
>
  <CreateVectorStoreForm
    {keyboard_submit}
    on:success={async (e) => {
      dispatch("success", {
        vector_store_config_id: e.detail.vector_store_config_id,
      })
    }}
  />
</Dialog>
