<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { Eval, EvalStatus } from "$lib/types"
  import { capitalize } from "$lib/utils/formatters"
  import EditableFieldBase from "./editable_field_base.svelte"

  // Status lives on the eval (the server resolves legacy spec-backed evals
  // on read, so `status` is always concrete here despite the nullable type).
  export let evaluator: Eval
  export let options: OptionGroup[]
  export let aria_label: string = "Status"
  export let onUpdate: (evaluator: Eval, value: EvalStatus) => void
  export let compact: boolean = false
  export let onOpen: (() => void) | undefined = undefined

  let baseComponent: EditableFieldBase<EvalStatus>
  let currentValue: EvalStatus = evaluator.status ?? "active"
  let lastSyncedValue: EvalStatus = currentValue

  $: {
    const evaluator_status = evaluator.status ?? "active"
    if (evaluator_status !== lastSyncedValue) {
      lastSyncedValue = evaluator_status
      currentValue = evaluator_status
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
  formatDisplay={capitalize}
  {onUpdate}
  dropdownWidth="w-32"
  {compact}
  {onOpen}
/>
