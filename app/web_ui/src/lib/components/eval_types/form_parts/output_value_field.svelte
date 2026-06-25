<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_section.svelte"

  export let value: string | null = null
  export let id_prefix: string
</script>

<FormSection
  title="Output Extraction"
  subtitle="Optionally extract a specific field from the model output before comparing."
  testid="output-value-section"
>
  <FormElement
    id="{id_prefix}_value_expression"
    label="Output Value to Compare"
    description="Leave blank to compare the entire model output, or use a Jinja expression to extract fields from JSON output."
    info_description="Jinja is a templating syntax for pulling values out of structured output. For example, use `user.email` to extract the email field from a JSON response."
    inputType="input"
    optional={true}
    hide_label={true}
    placeholder="e.g. result.answer"
    bind:value
  />
</FormSection>
