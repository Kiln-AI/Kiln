<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { Priority, Spec } from "$lib/types"
  import { formatPriority } from "$lib/utils/formatters"
  import EditableFieldBase from "./editable_field_base.svelte"

  export let spec: Spec
  export let options: OptionGroup[]
  export let aria_label: string = "Priority"
  export let onUpdate: (spec: Spec, value: Priority) => void
  export let compact: boolean = false
  export let onOpen: (() => void) | undefined = undefined

  let baseComponent: EditableFieldBase<Priority>
  let currentValue: Priority = spec.priority
  let lastSyncedSpecValue: Priority = spec.priority

  $: {
    if (spec.priority !== lastSyncedSpecValue) {
      lastSyncedSpecValue = spec.priority
      currentValue = spec.priority
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
  formatDisplay={formatPriority}
  {onUpdate}
  dropdownWidth="w-24"
  {compact}
  {onOpen}
/>
