<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"

  export let properties: components["schemas"]["StepCountCheckProperties"] = {
    type: "step_count_check",
    count_type: "tool_calls",
    min_count: null,
    max_count: null,
  }

  export function getProperties(): components["schemas"]["StepCountCheckProperties"] {
    return properties
  }

  export function validate(): string | null {
    if (properties.min_count == null && properties.max_count == null) {
      return "At least one of minimum or maximum count must be set."
    }
    if (
      properties.min_count != null &&
      properties.max_count != null &&
      properties.min_count > properties.max_count
    ) {
      return "Minimum count must be less than or equal to maximum count."
    }
    return null
  }
</script>

<div class="flex flex-col gap-4">
  <FormElement
    id="step_count_check_count_type"
    label="Count Type"
    description="What type of conversation step to count."
    inputType="select"
    bind:value={properties.count_type}
    select_options={[
      ["tool_calls", "Tool Calls"],
      ["model_responses", "Model Responses"],
      ["turns", "Turns"],
    ]}
  />

  <FormElement
    id="step_count_check_min"
    label="Minimum Count"
    description="The minimum number of steps required (leave empty for no minimum)."
    inputType="input_number"
    optional={true}
    bind:value={properties.min_count}
  />

  <FormElement
    id="step_count_check_max"
    label="Maximum Count"
    description="The maximum number of steps allowed (leave empty for no maximum)."
    inputType="input_number"
    optional={true}
    bind:value={properties.max_count}
  />
</div>
