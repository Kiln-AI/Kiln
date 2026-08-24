<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"

  export let value: unknown = null
  export let error_message: string | null = null
  export let inputType: "fancy_select" | "multi_select" = "fancy_select"
</script>

<FormElement
  {inputType}
  id="fancy_test_field"
  label="Dataset Filter Tag"
  {error_message}
  fancy_select_options={[
    { label: "Tags", options: [{ label: "fine_tune_a", value: "a" }] },
  ]}
  bind:value
/>
