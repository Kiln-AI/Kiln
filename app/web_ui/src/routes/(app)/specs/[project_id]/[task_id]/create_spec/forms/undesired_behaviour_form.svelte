<script lang="ts">
  import Warning from "$lib/ui/warning.svelte"
  import FormElement from "$lib/utils/form_element.svelte"

  let undesired_behaviour = "test"
  let examples: string = ""

  let suggestion_mode: boolean = true

  export let form_has_unsaved_changes: boolean = false
  $: form_has_unsaved_changes = !!(undesired_behaviour || examples)

  export function get_properties() {
    return {
      spec_type: "undesired_behaviour",
      undesired_behaviour_guidelines: undesired_behaviour,
      examples: examples,
    }
  }
</script>

{#if suggestion_mode}
  <div class="space-y-8">
    <!-- UNDERSIRED BEHAVIOUR GROUP -->
    <div class="flex flex-col border rounded-xl p-6 bg-white shadow-sm">
      <span class="text-md font-medium">Undesired Behaviour</span>
      <span class="text-sm text-gray-500 mb-4">
        A detailed description of the undesired behaviour you want to catch.
        This will be used by AI to understand the spec.
      </span>

      <FormElement
        label="Current"
        id="undesired_behaviour"
        inputType="textarea"
        bind:value={undesired_behaviour}
        disabled={true}
      />

      <div class="border-t mt-4 pt-4">
        <FormElement
          label="Suggestion"
          id="undesired_behaviour_suggestion"
          inputType="textarea"
          value="Test suggestion"
        />
      </div>
      <div class="mt-2">
        <Warning
          warning_message="This suggestion improves clarity and ensures the model understands exactly what behaviour is considered undesired."
          warning_color="success"
          warning_icon="question"
          large_icon={true}
          outline={true}
        />
      </div>
      <div class="flex flex-row gap-2 justify-end mt-4">
        <button class="btn btn-outline w-50">Reject Suggestion</button>
        <button class="btn btn-primary w-50">Accept Suggestion</button>
      </div>
    </div>

    <!-- EXAMPLES GROUP -->
    <div class="flex flex-col border rounded-xl p-6 bg-white shadow-sm">
      <span class="text-md font-medium">Examples</span>
      <span class="text-sm text-gray-500 mb-4">
        A list of examples of model behaviour that should fail the spec. This
        will be used by AI to understand the spec.
      </span>

      <FormElement
        label="Current"
        id="undesired_behaviour_list"
        inputType="textarea"
        bind:value={examples}
        disabled={true}
      />

      <div class="border-t mt-4 pt-4">
        <FormElement
          label="Suggestion"
          id="undesired_behaviour_list_suggestion"
          inputType="textarea"
          value="Test examples"
        />
      </div>
      <div class="mt-2">
        <Warning
          warning_message="This suggestion improves clarity and ensures the model understands exactly what behaviour is considered undesired."
          warning_color="success"
          warning_icon="question"
          large_icon={true}
          outline={true}
        />
      </div>
      <div class="flex flex-row gap-2 justify-end mt-4">
        <button class="btn btn-outline w-50">Reject Suggestion</button>
        <button class="btn btn-primary w-50">Accept Suggestion</button>
      </div>
    </div>
  </div>
{:else}
  <!-- NORMAL MODE -->
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
{/if}
