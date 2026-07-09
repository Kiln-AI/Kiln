<svelte:options accessors />

<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let value: string | null = null
  export let id_prefix: string
  export let candidate_keys: string[] = []

  const CUSTOM_SENTINEL = "__custom__"

  // ── True state (mutated only at user-event boundaries) ──

  // What the user typed in the plain text box.
  let text_input_value: string = value ?? ""

  // The key currently selected in the dropdown.
  // Empty string means "no selection" — FancySelect shows its empty_label.
  // CUSTOM_SENTINEL is never persisted; it is a momentary trigger for the modal.
  let selected: string = value ?? ""

  // Keys the user explicitly added via the Custom Field Name modal.
  let modal_added_keys: string[] = []

  // ── Derived (read-only reactive — no imperative writes) ──

  // Show dropdown when there are candidate keys or modal-added keys.
  $: show_select = candidate_keys.length > 0 || modal_added_keys.length > 0

  // When in text-input mode, keep `selected` mirrored to what the user
  // typed. This is purely derived: "if there's no dropdown, the dropdown
  // selection is whatever the user typed." When candidates appear and the
  // dropdown mounts, `selected` already points at the typed value.
  $: if (!show_select) {
    selected = text_input_value.trim() || ""
  }

  // Deduplicated option list. text_input_value is ALWAYS included (when
  // non-empty), so when candidates appear the dropdown automatically
  // contains whatever the user typed — no migration code needed.
  $: selectOptions = build_options(
    candidate_keys,
    modal_added_keys,
    text_input_value,
  )

  function build_options(
    keys: string[],
    modal_keys: string[],
    typed: string,
  ): OptionGroup[] {
    const trimmed_typed = typed.trim()
    const seen = new Set<string>()
    const opts: Array<{ value: string; label: string }> = []
    for (const k of [
      ...keys,
      ...modal_keys,
      ...(trimmed_typed ? [trimmed_typed] : []),
    ]) {
      if (!seen.has(k)) {
        seen.add(k)
        opts.push({ value: k, label: k })
      }
    }
    return [
      {
        options: [
          ...opts,
          {
            value: CUSTOM_SENTINEL,
            label: "Custom Field Name",
            description: "Enter a field name manually.",
          },
        ],
      },
    ]
  }

  // ── Emit: single block pushes internal state → value prop ──

  let last_emitted: string | null = value

  $: {
    const next = show_select
      ? selected && selected !== CUSTOM_SENTINEL
        ? selected
        : null
      : text_input_value.trim() || null

    if (next !== last_emitted) {
      last_emitted = next
      value = next
    }
  }

  // ── External value sync (parent bind or $set) ──

  function syncFromValue() {
    const v = value
    if (v) {
      text_input_value = v
      selected = v
    } else {
      text_input_value = ""
      selected = ""
    }
    last_emitted = v
  }

  $: if (value !== last_emitted) {
    syncFromValue()
  }

  // ── Modal flow: detect sentinel selection ──

  let prev_selected: string = selected

  $: if (selected !== prev_selected) {
    const old = prev_selected
    prev_selected = selected
    if (selected === CUSTOM_SENTINEL && show_select) {
      pre_modal_selected = old
      // Immediately revert so the sentinel never lingers as a visible label.
      selected = old
      prev_selected = old
      open_custom_modal()
    }
  }

  // ── Custom Field Name modal ──

  let custom_dialog: Dialog
  let custom_dialog_value = ""
  let custom_dialog_error: string | null = null
  let pre_modal_selected: string = ""

  function open_custom_modal() {
    custom_dialog_value = ""
    custom_dialog_error = null
    custom_dialog?.show()
  }

  function handle_custom_submit(): boolean {
    const trimmed = custom_dialog_value.trim()
    if (!trimmed) {
      custom_dialog_error = "Field name is required."
      return false
    }
    custom_dialog_error = null
    if (!modal_added_keys.includes(trimmed)) {
      modal_added_keys = [...modal_added_keys, trimmed]
    }
    text_input_value = trimmed
    selected = trimmed
    prev_selected = trimmed
    value = trimmed
    last_emitted = trimmed
    return true
  }

  function handle_custom_cancel() {
    selected = pre_modal_selected
    prev_selected = pre_modal_selected
  }
</script>

{#if show_select}
  <FormElement
    id="{id_prefix}_reference_key"
    label="Reference Data Field"
    inputType="fancy_select"
    fancy_select_options={selectOptions}
    description="The field in your reference data holding the expected value to compare against."
    info_description="A top-level field in your reference data, e.g. `expected_answer` or `expected_status`."
    bind:value={selected}
  />

  <Dialog
    bind:this={custom_dialog}
    title="Custom Field Name"
    subtitle="Enter the name of a field in your reference data."
    action_buttons={[
      {
        label: "Add",
        isPrimary: true,
        action: handle_custom_submit,
      },
    ]}
    on:cancel={handle_custom_cancel}
  >
    <div class="flex flex-col gap-3">
      <input
        type="text"
        class="input input-bordered w-full font-mono text-sm"
        placeholder="e.g. expected_answer"
        bind:value={custom_dialog_value}
        data-testid="custom-field-name-input"
      />
      {#if custom_dialog_error}
        <div class="text-error text-xs" data-testid="custom-field-name-error">
          {custom_dialog_error}
        </div>
      {/if}
    </div>
  </Dialog>
{:else}
  <FormElement
    id="{id_prefix}_reference_key"
    label="Reference Data Field"
    inputType="input"
    placeholder="e.g. expected_answer"
    description="The field in your reference data holding the expected value to compare against."
    info_description="A top-level field in your reference data, e.g. `expected_answer` or `expected_status`."
    bind:value={text_input_value}
  />
{/if}
