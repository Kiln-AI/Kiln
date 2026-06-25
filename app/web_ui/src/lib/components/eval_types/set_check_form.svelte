<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_parts/form_section.svelte"
  import DisclosureRadioGroup from "./form_parts/disclosure_radio_group.svelte"
  import OutputValueField from "./form_parts/output_value_field.svelte"
  import TagInput from "./tag_input.svelte"

  export let properties: components["schemas"]["SetCheckProperties"] = {
    type: "set_check",
    mode: "equal",
    value_expression: null,
    expected_set: [],
    reference_key: null,
  }

  export function getProperties(): components["schemas"]["SetCheckProperties"] {
    if (source === "reference_key") {
      return { ...properties, expected_set: null }
    }
    return { ...properties, reference_key: null }
  }

  export function validate(): string | null {
    if (
      source === "expected_set" &&
      (!properties.expected_set || properties.expected_set.length === 0)
    ) {
      return "Expected set must contain at least one value."
    }
    if (source === "reference_key" && !properties.reference_key) {
      return "Reference key is required."
    }
    return null
  }

  let source: "expected_set" | "reference_key" = properties.reference_key
    ? "reference_key"
    : "expected_set"

  function on_source_change() {
    if (source === "expected_set") {
      properties.reference_key = null
    } else {
      properties.expected_set = null
      expected_set_tags = []
    }
  }

  let expected_set_tags: string[] = properties.expected_set ?? []
  $: properties.expected_set = expected_set_tags
</script>

<div class="flex flex-col gap-6">
  <FormSection
    title="Expected Set"
    subtitle="Define the set of values to compare against the output."
    testid="set-check-expected-section"
  >
    <DisclosureRadioGroup
      name="set_check_source"
      options={[
        {
          value: "expected_set",
          label: "Fixed set",
          description: "Specify the expected set of values directly.",
        },
        {
          value: "reference_key",
          label: "Value from reference data",
          description:
            "Use a key from the reference data containing the expected set.",
        },
      ]}
      bind:selected={source}
      on:change={on_source_change}
    />

    {#if source === "expected_set"}
      <TagInput
        id="set_check_expected_set"
        bind:tags={expected_set_tags}
        placeholder="Type a value and press Enter"
      />
      <p class="text-xs text-gray-500 -mt-2">
        Add items by typing and pressing Enter or comma.
      </p>
    {:else}
      <FormElement
        id="set_check_reference_key"
        label="Reference Key"
        description="The key in the reference data containing the expected set."
        inputType="input"
        bind:value={properties.reference_key}
      />
    {/if}
  </FormSection>

  <FormSection
    title="Comparison Mode"
    subtitle="How to compare the output set against the expected set."
    testid="set-check-mode-section"
  >
    <DisclosureRadioGroup
      name="set_check_mode"
      options={[
        {
          value: "equal",
          label: "Equal",
          description:
            "The output set must contain exactly the same elements as the expected set.",
        },
        {
          value: "subset",
          label: "Subset",
          description:
            "The output set must be a subset of the expected set (all output values appear in expected).",
        },
        {
          value: "superset",
          label: "Superset",
          description:
            "The output set must be a superset of the expected set (all expected values appear in output).",
        },
      ]}
      bind:selected={properties.mode}
    />
  </FormSection>

  <OutputValueField
    id_prefix="set_check"
    bind:value={properties.value_expression}
  />
</div>
