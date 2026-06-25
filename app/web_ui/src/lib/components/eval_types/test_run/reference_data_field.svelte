<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"

  export let reference_data: string = ""

  let dialog: Dialog
  let edit_value = ""
  let json_error: string | null = null

  const dispatch = createEventDispatcher<{
    change: string
  }>()

  $: display_value = get_display_value(reference_data)

  function get_display_value(data: string): string {
    if (!data.trim()) return "None"
    try {
      const parsed = JSON.parse(data.trim())
      const keys = Object.keys(parsed)
      if (keys.length === 0) return "Empty object"
      if (keys.length <= 3) return keys.join(", ")
      return `${keys.slice(0, 3).join(", ")} +${keys.length - 3} more`
    } catch {
      return "Invalid JSON"
    }
  }

  function open_editor() {
    edit_value = reference_data
    json_error = null
    dialog?.show()
  }

  function handle_save(): boolean {
    if (!edit_value.trim()) {
      dispatch("change", "")
      return true
    }
    try {
      JSON.parse(edit_value.trim())
      json_error = null
      dispatch("change", edit_value.trim())
      return true
    } catch (e) {
      json_error =
        e instanceof Error
          ? e.message
          : "Invalid JSON. Please check your input."
      return false
    }
  }
</script>

<div
  class="flex items-center justify-between text-sm py-1"
  data-testid="reference-data-field"
>
  <span class="text-base-content/60">Reference Data</span>
  <button
    type="button"
    class="link text-sm text-base-content/60 hover:text-primary"
    on:click={open_editor}
    data-testid="reference-data-edit"
  >
    {display_value}
  </button>
</div>

<Dialog
  bind:this={dialog}
  title="Reference Data"
  subtitle="Provide a JSON object with reference values for this test run."
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Save",
      isPrimary: true,
      action: handle_save,
    },
  ]}
>
  <div class="flex flex-col gap-3">
    <textarea
      class="textarea textarea-bordered w-full font-mono text-sm"
      rows="8"
      placeholder={'{"expected_answer": "..."}'}
      bind:value={edit_value}
      data-testid="reference-data-textarea"
    ></textarea>
    {#if json_error}
      <div class="text-error text-xs" data-testid="reference-data-error">
        {json_error}
      </div>
    {/if}
  </div>
</Dialog>
