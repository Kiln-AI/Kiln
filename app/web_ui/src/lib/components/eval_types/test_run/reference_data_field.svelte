<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"

  export let reference_data: string = ""

  let dialog: Dialog
  let rows: Array<{ key: string; value: string }> = []
  let save_error: string | null = null

  const dispatch = createEventDispatcher<{
    change: string
  }>()

  $: display_value = get_display_value(reference_data)

  function is_plain_object(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value)
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

  function parse_value(raw: string): unknown {
    try {
      return JSON.parse(raw)
    } catch {
      return raw
    }
  }

  function object_to_rows(data: string): Array<{ key: string; value: string }> {
    if (!data.trim()) return []
    try {
      const parsed = JSON.parse(data.trim())
      if (!is_plain_object(parsed)) return []
      return Object.entries(parsed).map(([key, val]) => ({
        key,
        value: JSON.stringify(val),
      }))
    } catch {
      return []
    }
  }

  function open_editor() {
    rows = object_to_rows(reference_data)
    if (rows.length === 0) {
      rows = [{ key: "", value: "" }]
    }
    save_error = null
    dialog?.show()
  }

  function add_row() {
    rows = [...rows, { key: "", value: "" }]
  }

  function remove_row(index: number) {
    rows = rows.filter((_, i) => i !== index)
  }

  function handle_save(): boolean {
    // Filter out completely empty rows
    const filled = rows.filter((r) => r.key.trim() || r.value.trim())

    if (filled.length === 0) {
      dispatch("change", "")
      return true
    }

    // Check for empty keys on rows that have values
    const empty_key = filled.find((r) => !r.key.trim())
    if (empty_key) {
      save_error = "Each row must have a name."
      return false
    }

    // Check for duplicate keys
    const keys = filled.map((r) => r.key.trim())
    const unique_keys = new Set(keys)
    if (unique_keys.size !== keys.length) {
      save_error = "Duplicate names are not allowed."
      return false
    }

    const obj: Record<string, unknown> = {}
    for (const row of filled) {
      obj[row.key.trim()] = parse_value(row.value)
    }

    save_error = null
    dispatch("change", JSON.stringify(obj))
    return true
  }
</script>

<div
  class="flex items-center justify-between text-sm py-1"
  data-testid="reference-data-field"
>
  <span class="text-gray-500">Reference Data</span>
  <button
    type="button"
    class="link text-sm text-gray-500 hover:text-primary"
    on:click={open_editor}
    data-testid="reference-data-edit"
  >
    {display_value}
  </button>
</div>

<Dialog
  bind:this={dialog}
  title="Reference Data"
  subtitle="Provide key-value pairs for reference data used during evaluation."
  width="wide"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Save",
      isPrimary: true,
      action: handle_save,
    },
  ]}
>
  <div class="flex flex-col gap-3" data-testid="reference-data-editor">
    {#if rows.length === 0}
      <p class="text-sm text-gray-500">
        No values yet. Add one to get started.
      </p>
    {/if}

    {#each rows as row, index}
      <div class="flex items-start gap-2" data-testid="reference-data-row">
        <div class="flex-1">
          {#if index === 0}
            <div class="py-0 pb-1">
              <span class="label-text text-xs">Name</span>
            </div>
          {/if}
          <input
            type="text"
            class="input input-bordered input-sm w-full"
            placeholder="key"
            bind:value={row.key}
            data-testid="reference-data-key"
          />
        </div>
        <div class="flex-[2]">
          {#if index === 0}
            <div class="py-0 pb-1">
              <span class="label-text text-xs">Value</span>
            </div>
          {/if}
          <input
            type="text"
            class="input input-bordered input-sm w-full font-mono"
            placeholder="value"
            bind:value={row.value}
            data-testid="reference-data-value"
          />
        </div>
        <div class={index === 0 ? "mt-6" : ""}>
          <button
            type="button"
            class="btn btn-ghost btn-sm btn-square"
            on:click={() => remove_row(index)}
            aria-label="Remove row"
            data-testid="reference-data-remove"
          >
            <i class="bi bi-x-lg text-gray-400"></i>
          </button>
        </div>
      </div>
    {/each}

    <div>
      <button
        type="button"
        class="btn btn-ghost btn-sm text-primary"
        on:click={add_row}
        data-testid="reference-data-add"
      >
        <i class="bi bi-plus-lg"></i>
        Add Value
      </button>
    </div>

    {#if save_error}
      <div class="text-error text-xs" data-testid="reference-data-error">
        {save_error}
      </div>
    {/if}
  </div>
</Dialog>
