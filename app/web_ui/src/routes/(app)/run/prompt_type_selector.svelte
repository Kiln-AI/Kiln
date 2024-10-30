<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"

  export let prompt_method: string
</script>

<FormElement
  label="Prompt Method"
  inputType="select"
  bind:value={prompt_method}
  id="prompt_method"
  select_options={[
    ["basic", "Basic Prompt (Zero Shot)"],
    ["few_shot", "Few Shot"],
    ["many_shot", "Many Shot"],
    ["repairs", "Repair Multi Shot"],
  ]}
/>
