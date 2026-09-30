<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { Eval, Priority } from "$lib/types"
  import { formatPriority } from "$lib/utils/formatters"
  import EditableFieldBase from "./editable_field_base.svelte"

  // Priority lives on the eval (the server resolves legacy spec-backed evals
  // on read, so `priority` is always concrete here despite the nullable type).
  export let evaluator: Eval
  export let options: OptionGroup[]
  export let aria_label: string = "Priority"
  export let onUpdate: (evaluator: Eval, value: Priority) => void
  export let compact: boolean = false
  export let onOpen: (() => void) | undefined = undefined

  let baseComponent: EditableFieldBase<Priority>
  let currentValue: Priority = evaluator.priority ?? 1
  let lastSyncedValue: Priority = currentValue

  $: {
    const evaluator_priority = evaluator.priority ?? 1
    if (evaluator_priority !== lastSyncedValue) {
      lastSyncedValue = evaluator_priority
      currentValue = evaluator_priority
      baseComponent?.setPendingComplete()
    }
  }

  $: if (currentValue !== lastSyncedValue && baseComponent) {
    baseComponent.triggerUpdate()
  }

  export function close() {
    baseComponent?.close()
  }
</script>

<EditableFieldBase
  bind:this={baseComponent}
  {evaluator}
  bind:currentValue
  {options}
  {aria_label}
  formatDisplay={formatPriority}
  {onUpdate}
  dropdownWidth="w-24"
  {compact}
  {onOpen}
/>
