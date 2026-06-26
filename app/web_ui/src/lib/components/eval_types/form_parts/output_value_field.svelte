<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"

  export let value: string | null = null
  export let id_prefix: string
  export let extra_description: string = ""

  const base_description =
    "A field in the output to compare to expected value, example: `user.status`. Leave blank to compare entire output."
  $: full_description = extra_description
    ? `${base_description} ${extra_description}`
    : base_description
</script>

<FormElement
  id="{id_prefix}_value_expression"
  label="Output Value"
  description={full_description}
  info_description="Extract a value from the model output. For example, use `user.email` to extract the email field from a JSON response. Uses Jinja extractor syntax."
  inputType="input"
  optional={true}
  placeholder="e.g. result.answer"
  bind:value
/>
