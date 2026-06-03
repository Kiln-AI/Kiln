<svelte:options accessors />

<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { InputTransform } from "$lib/types"
  import InputTransformCreateModal from "./input_transform_create_modal.svelte"

  export let input_transform: InputTransform | null = null

  let create_modal: InputTransformCreateModal
  let select_value: "none" | "custom" = input_transform ? "custom" : "none"

  $: options = build_options(input_transform)

  function build_options(transform: InputTransform | null): OptionGroup[] {
    return [
      {
        label: "Input Transform",
        action_label: transform ? "Edit Template" : "Create Template",
        action_handler: () =>
          create_modal.show(
            transform?.type === "jinja" ? transform.template : "",
          ),
        options: [
          { value: "none", label: "None" },
          ...(transform ? [{ value: "custom", label: "Custom Template" }] : []),
        ],
      },
    ]
  }

  $: handle_select(select_value)

  function handle_select(v: "none" | "custom") {
    if (v === "none" && input_transform !== null) {
      input_transform = null
    }
  }

  $: select_value = input_transform ? "custom" : "none"

  function on_created(t: InputTransform) {
    input_transform = t
  }
</script>

<FormElement
  id="input_transform"
  label="Input Transform"
  inputType="fancy_select"
  bind:value={select_value}
  fancy_select_options={options}
  info_description="Transform the provided input before sending the input to the model. Allows you to add context, or filter data."
/>

<InputTransformCreateModal bind:this={create_modal} {on_created} />
