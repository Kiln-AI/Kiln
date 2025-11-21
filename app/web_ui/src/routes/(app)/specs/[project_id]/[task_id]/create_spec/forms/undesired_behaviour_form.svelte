<script lang="ts">
  import CreateSpecForm from "./create_spec_form.svelte"
  import FormElement from "$lib/utils/form_element.svelte"

  let undesired_behaviour = ""
  let examples: string = ""
</script>

<CreateSpecForm
  spec_type="undesired_behaviour"
  form_has_unsaved_changes={!!(undesired_behaviour || examples)}
  get_properties={() => ({
    spec_type: "undesired_behaviour",
    undesired_behaviour_guidelines: undesired_behaviour,
    examples: examples,
  })}
>
  <svelte:fragment slot="form_elements">
    <FormElement
      label="Undesired Behaviour"
      description="A detailed description of the undesired behaviour you want to catch. This will be used by AI to understand the spec."
      id="undesired_behaviour"
      inputType="textarea"
      bind:value={undesired_behaviour}
    />
    <FormElement
      label="Examples"
      description="A list of examples of model behaviour that should fail the spec. This will be used by AI to understand the spec."
      id="undesired_behaviour_list"
      inputType="textarea"
      bind:value={examples}
    />
  </svelte:fragment>
</CreateSpecForm>
