<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"

  export let value: string = ""
  export let label: string = "Test Label"
  export let description: string = ""
  export let info_description: string = ""
  export let error_message: string | null = null
  export let hide_label: boolean = false
</script>

<FormElement
  inputType="input"
  id="test_hide_label"
  {label}
  {description}
  {info_description}
  {error_message}
  {hide_label}
  bind:value
/>
