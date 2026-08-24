<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"

  export let value: string = ""
  export let label: string = "Full Name"
  export let placeholder: string | null = null
  export let error_message: string | null = null
  export let inputType: "input" | "textarea" | "select" = "input"
</script>

<FormElement
  {inputType}
  id="aria_test_field"
  {label}
  {placeholder}
  {error_message}
  select_options={[
    ["a", "Option A"],
    ["b", "Option B"],
  ]}
  bind:value
/>
