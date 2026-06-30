<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"

  export let reference_data: string = ""
  export let required_reference_fields: string[] = []

  let dialog: Dialog
  let edit_value = ""
  let json_error: string | null = null

  const dispatch = createEventDispatcher<{
    change: string
  }>()

  $: missing_fields = get_missing_fields(
    reference_data,
    required_reference_fields,
  )
  $: display_value =
    missing_fields.length > 0
      ? "Missing " + missing_fields.join(", ")
      : get_display_value(reference_data)
  $: display_is_error = missing_fields.length > 0

  function is_plain_object(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value)
  }

  function get_missing_fields(data: string, required: string[]): string[] {
    if (required.length === 0) return []
    if (!data.trim()) return required
    try {
      const parsed = JSON.parse(data.trim())
      if (!is_plain_object(parsed)) return required
      return required.filter(
        (k) =>
          !(k in parsed) ||
          parsed[k] === undefined ||
          parsed[k] === null ||
          parsed[k] === "",
      )
    } catch {
      return required
    }
  }

  function get_display_value(data: string): string {
    if (!data.trim()) return "None"
    try {
      const parsed = JSON.parse(data.trim())
      if (!is_plain_object(parsed)) return "Invalid: not an object"
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
      const parsed = JSON.parse(edit_value.trim())
      if (!is_plain_object(parsed)) {
        json_error =
          'Reference data must be a JSON object, e.g. {"key": "value"}.'
        return false
      }
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
  <span class="text-gray-500">Reference Data</span>
  <button
    type="button"
    class="link text-sm {display_is_error
      ? 'text-error'
      : 'text-gray-500 hover:text-primary'}"
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
