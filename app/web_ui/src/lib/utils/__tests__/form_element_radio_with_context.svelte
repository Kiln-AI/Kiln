<script lang="ts">
  import { setContext } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import type { RadioOption } from "$lib/utils/form_element.svelte"

  export let value: string = ""
  export let radio_options: RadioOption[] = []
  export let optional: boolean = false
  export let label: string = "Test Radio"
  export let description: string = ""
  export let info_description: string = ""
  export let disabled: boolean = false

  type FormElementValidator = {
    run_validator: () => void
  }

  let registeredElements: FormElementValidator[] = []

  function registerFormElement(validator: FormElementValidator) {
    registeredElements.push(validator)
    return () => {
      const index = registeredElements.indexOf(validator)
      if (index > -1) {
        registeredElements.splice(index, 1)
      }
    }
  }

  setContext("form_container", { registerFormElement })

  export function getRegisteredCount(): number {
    return registeredElements.length
  }

  export function runAllValidators(): void {
    registeredElements.forEach((el) => el.run_validator())
  }

  let formElement: FormElement

  export function runValidator(): void {
    formElement.run_validator()
  }
</script>

<div data-testid="context-wrapper">
  <FormElement
    bind:this={formElement}
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
</div>
