<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import type { RadioOption } from "$lib/utils/form_element.svelte"

  export let value: string = ""
  export let radio_options: RadioOption[] = []
  export let optional: boolean = false
  export let label: string = "Test Radio"
  export let description: string = ""
  export let info_description: string = ""
  export let disabled: boolean = false

  let form_container: FormContainer

  export async function validate_only(): Promise<boolean> {
    return form_container.validate_only()
  }
</script>

<FormContainer
  bind:this={form_container}
  submit_label="Submit"
  focus_on_mount={false}
  on:submit
>
  <FormElement
    inputType="radio"
    id="test_radio"
    {label}
    {description}
    {info_description}
    {optional}
    {disabled}
    {radio_options}
    bind:value
  />
</FormContainer>
