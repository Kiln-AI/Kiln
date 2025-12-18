<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { SpecStatus, Spec } from "$lib/types"
  import { capitalize } from "$lib/utils/formatters"
  import EditableFieldBase from "./editable_field_base.svelte"

  export let spec: Spec
  export let options: OptionGroup[]
  export let aria_label: string = "Status"
  export let onUpdate: (spec: Spec, value: SpecStatus) => void
  export let compact: boolean = false
  export let onOpen: (() => void) | undefined = undefined
  export let always_show_border: boolean = false

  let baseComponent: EditableFieldBase<SpecStatus>
  let currentValue: SpecStatus = spec.status
  let lastSyncedSpecValue: SpecStatus = spec.status

  $: {
    if (spec.status !== lastSyncedSpecValue) {
      lastSyncedSpecValue = spec.status
      currentValue = spec.status
      baseComponent?.setPendingComplete()
    }
  }

  $: if (currentValue !== lastSyncedSpecValue && baseComponent) {
    baseComponent.triggerUpdate()
  }

  export function close() {
    baseComponent?.close()
  }
</script>

<EditableFieldBase
  bind:this={baseComponent}
  {spec}
  bind:currentValue
  {options}
  {aria_label}
  formatDisplay={capitalize}
  {onUpdate}
  dropdownWidth="w-32"
  {compact}
  {onOpen}
  {always_show_border}
/>
