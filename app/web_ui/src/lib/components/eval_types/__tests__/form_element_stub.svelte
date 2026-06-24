<script lang="ts">
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

  export let validator: (value: unknown) => string | null = () => null
  export function run_validator() {
    error_message = validator(value)
  }
</script>

<div data-testid="form-element-{id}" data-label={label} data-type={inputType}>
  <slot />
</div>
