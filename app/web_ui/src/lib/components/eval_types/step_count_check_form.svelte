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
      return "At least one bound must be set."
    }
    if (
      properties.min_count != null &&
      properties.max_count != null &&
      properties.min_count > properties.max_count
    ) {
      return "Minimum must be less than or equal to maximum."
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
    subtitle="Choose what to count in the agent's trace."
    testid="step-count-type-section"
  >
    <FormElement
      id="step_count_check_count_type"
      inputType="radio"
      radio_options={[
        {
          value: "tool_calls",
          label: "Tool calls",
          description: "Count each tool or function call the agent made.",
        },
        {
          value: "model_responses",
          label: "Model responses",
          description:
            "Count each response the model generated (one per inference call).",
        },
        {
          value: "turns",
          label: "Turns",
          description:
            "Count conversational turns (each user-then-assistant exchange counts as one turn).",
        },
      ]}
      bind:value={properties.count_type}
      hide_label
    />
  </FormSection>

  <FormSection
    title="Bounds"
    subtitle="Set a minimum and/or maximum. At least one is required."
    testid="step-count-bounds-section"
  >
    <div class="ml-4 border-l border-base-300 pl-4">
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div on:blur={on_bounds_blur}>
        <div class="flex gap-4" data-testid="bounds-row">
          <div class="flex-1">
            <FormElement
              id="step_count_check_min"
              label="Minimum"
              inputType="input_number"
              optional={true}
              placeholder="No minimum"
              bind:value={properties.min_count}
              min={0}
            />
          </div>
          <div class="flex-1">
            <FormElement
              id="step_count_check_max"
              label="Maximum"
              inputType="input_number"
              optional={true}
              placeholder="No maximum"
              bind:value={properties.max_count}
              min={0}
            />
          </div>
        </div>
        {#if bounds_error}
          <p class="text-error text-xs mt-1" data-testid="bounds-error">
            {bounds_error}
          </p>
        {/if}
      </div>
    </div>
  </FormSection>
</div>
