<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_parts/form_section.svelte"
  import OutputValueField from "./form_parts/output_value_field.svelte"

  export let properties: components["schemas"]["ExactMatchProperties"] = {
    type: "exact_match",
    case_sensitive: true,
    value_expression: null,
    expected_value: null,
    reference_key: null,
  }

  export function getProperties(): components["schemas"]["ExactMatchProperties"] {
    return properties
  }

  export function validate(): string | null {
    if (source === "expected_value" && !properties.expected_value) {
      return "Expected value is required."
    }
    if (source === "reference_key" && !properties.reference_key) {
      return "Reference key is required."
    }
    return null
  }

  let source: "expected_value" | "reference_key" = properties.expected_value
    ? "expected_value"
    : properties.reference_key
      ? "reference_key"
      : "expected_value"

  function on_source_change() {
    if (source === "expected_value") {
      properties.reference_key = null
    } else {
      properties.expected_value = null
    }
  }
</script>

<div class="flex flex-col gap-6">
  <FormSection title="Expected Value" testid="exact-match-expected-section">
    <FormElement
      id="exact_match_source"
      inputType="radio"
      radio_options={[
        {
          value: "expected_value",
          label: "Fixed value",
          description: "Enter the exact value the output should match.",
        },
        {
          value: "reference_key",
          label: "From reference data",
          description:
            "Look up the expected value from your dataset's reference fields.",
        },
      ]}
      bind:value={source}
      on_radio_change={on_source_change}
      hide_label
    />

    {#if source === "expected_value"}
      <div class="ml-4 border-l border-base-300 pl-4">
        <FormElement
          id="exact_match_expected_value"
          label="Expected Value"
          inputType="input"
          hide_label={true}
          placeholder="e.g. yes"
          bind:value={properties.expected_value}
        />
      </div>
    {:else}
      <div class="ml-4 border-l border-base-300 pl-4">
        <FormElement
          id="exact_match_reference_key"
          label="Reference Key"
          inputType="input"
          hide_label={true}
          placeholder="e.g. expected_answer"
          info_description="Reference data is the ground-truth data attached to each dataset example. Enter the key name whose value should be used as the expected answer."
          bind:value={properties.reference_key}
        />
      </div>
    {/if}
  </FormSection>

  <FormSection title="Comparison Options" testid="exact-match-options-section">
    <FormElement
      id="exact_match_case_sensitive"
      label="Case Sensitive"
      inputType="checkbox"
      bind:value={properties.case_sensitive}
    />
  </FormSection>

  <OutputValueField
    id_prefix="exact_match"
    bind:value={properties.value_expression}
  />
</div>
