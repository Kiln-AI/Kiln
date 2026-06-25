<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_parts/form_section.svelte"

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

  let bounds_error: string | null = null
  let bounds_touched = false

  function on_bounds_blur() {
    bounds_touched = true
    check_bounds(properties.min_count, properties.max_count)
  }

  function check_bounds(
    min: number | null | undefined,
    max: number | null | undefined,
  ) {
    if (min != null && max != null && min > max) {
      bounds_error = "Minimum must be ≤ maximum."
    } else {
      bounds_error = null
    }
  }

  $: if (bounds_touched) {
    check_bounds(properties.min_count, properties.max_count)
  }
</script>

<div class="flex flex-col gap-6">
  <FormSection
    title="What to Count"
    subtitle="Choose what type of step to count in the agent's trace."
    testid="step-count-type-section"
  >
    <FormElement
      id="step_count_check_count_type"
      inputType="radio"
      radio_options={[
        {
          value: "tool_calls",
          label: "Tool calls",
          description:
            "Count the number of tool/function calls the agent made.",
        },
        {
          value: "model_responses",
          label: "Model responses",
          description: "Count the number of responses the model generated.",
        },
        {
          value: "turns",
          label: "Turns",
          description: "Count the number of conversational turns in the trace.",
        },
      ]}
      bind:value={properties.count_type}
      hide_label
    />
  </FormSection>

  <FormSection
    title="Bounds"
    subtitle="Set a minimum and/or maximum count. At least one is required."
    testid="step-count-bounds-section"
  >
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div on:blur={on_bounds_blur}>
      <FormElement
        id="step_count_check_min"
        label="Minimum Count"
        description="The minimum number of steps required (leave empty for no minimum)."
        inputType="input_number"
        optional={true}
        bind:value={properties.min_count}
        error_message={bounds_error}
        min={0}
      />
    </div>

    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div on:blur={on_bounds_blur}>
      <FormElement
        id="step_count_check_max"
        label="Maximum Count"
        description="The maximum number of steps allowed (leave empty for no maximum)."
        inputType="input_number"
        optional={true}
        bind:value={properties.max_count}
        error_message={bounds_error}
        min={0}
      />
    </div>
  </FormSection>
</div>
