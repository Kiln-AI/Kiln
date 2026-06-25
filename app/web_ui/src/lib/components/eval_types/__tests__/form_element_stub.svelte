<script lang="ts">
  import type { InlineAction } from "$lib/utils/form_element.svelte"

  export let id: string = ""
  export let label: string = ""
  export let value: unknown = ""
  export let description: string = ""
  export let inputType: string = "input"
  export let optional: boolean = false
  export let select_options: unknown[] = []
  export let error_message: string | null = null
  export let info_description: string = ""
  export let on_select: () => void = () => {}
  export let disabled: boolean = false
  export let min: number | null = null
  export let max: number | null = null
  export let placeholder: string | null = null
  export let hide_optional_badge: boolean = false
  export let hide_label: boolean = false
  export let aria_label: string | null = null
  export let inline_action: InlineAction | null = null

  export let validator: (value: unknown) => string | null = () => null
  export function run_validator() {
    error_message = validator(value)
  }
</script>

<div
  data-testid="form-element-{id}"
  data-label={label}
  data-type={inputType}
  data-description={description}
  data-info-description={info_description}
  data-inline-action-label={inline_action?.label || ""}
>
  <slot />
</div>
