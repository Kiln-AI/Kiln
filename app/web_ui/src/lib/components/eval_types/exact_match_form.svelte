<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_parts/form_section.svelte"
  import DisclosureRadioGroup from "./form_parts/disclosure_radio_group.svelte"
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
  <FormSection
    title="Expected Value"
    subtitle="Choose what value to compare the output against."
    testid="exact-match-expected-section"
  >
    <DisclosureRadioGroup
      name="exact_match_source"
      options={[
        {
          value: "expected_value",
          label: "Fixed value",
          description: "Specify the exact value the output must match.",
        },
        {
          value: "reference_key",
          label: "Value from reference data",
          description:
            "Use a key from the reference data whose value the output must match.",
        },
      ]}
      bind:selected={source}
      on:change={on_source_change}
    />

    {#if source === "expected_value"}
      <FormElement
        id="exact_match_expected_value"
        label="Expected Value"
        inputType="input"
        bind:value={properties.expected_value}
      />
    {:else}
      <FormElement
        id="exact_match_reference_key"
        label="Reference Key"
        description="The key in the reference data to compare against."
        inputType="input"
        bind:value={properties.reference_key}
      />
    {/if}
  </FormSection>

  <OutputValueField
    id_prefix="exact_match"
    bind:value={properties.value_expression}
  >
    <FormElement
      id="exact_match_case_sensitive"
      label="Case Sensitive"
      inputType="checkbox"
      bind:value={properties.case_sensitive}
    />
  </OutputValueField>
</div>
