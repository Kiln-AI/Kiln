<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_parts/form_section.svelte"
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
    title="Expected Values"
    subtitle="Define what the output should contain."
    testid="set-check-expected-section"
  >
    <FormElement
      id="set_check_source"
      inputType="radio"
      radio_options={[
        {
          value: "expected_set",
          label: "Fixed values",
          description: "Enter the expected values directly.",
        },
        {
          value: "reference_key",
          label: "From reference data",
          description:
            "Look up the expected values from your dataset's reference fields.",
        },
      ]}
      bind:value={source}
      on_radio_change={on_source_change}
      hide_label
    />

    {#if source === "expected_set"}
      <div class="ml-4 border-l border-base-300 pl-4">
        <label
          for="set_check_expected_set"
          class="text-sm font-medium"
          data-testid="tag-input-label"
        >
          Expected Values
        </label>
        <p class="text-xs text-gray-500 mt-0.5 mb-1.5">
          Add items by typing and pressing Enter or comma.
        </p>
        <TagInput
          id="set_check_expected_set"
          bind:tags={expected_set_tags}
          placeholder="Type a value and press Enter"
        />
      </div>
    {:else}
      <div class="ml-4 border-l border-base-300 pl-4">
        <FormElement
          id="set_check_reference_key"
          label="Reference Key"
          info_description="Reference data is the ground-truth data attached to each dataset example. Enter the key name whose value should be used as the expected values."
          inputType="input"
          hide_label={true}
          placeholder="e.g. expected_values"
          bind:value={properties.reference_key}
        />
      </div>
    {/if}
  </FormSection>

  <FormSection title="Comparison Mode" testid="set-check-mode-section">
    <FormElement
      id="set_check_mode"
      inputType="radio"
      radio_options={[
        {
          value: "equal",
          label: "Equal",
          description:
            "The output must contain exactly the expected values, with no extras and nothing missing.",
        },
        {
          value: "subset",
          label: "Subset",
          description:
            "Every output value must appear in the expected values (extras in expected are OK).",
        },
        {
          value: "superset",
          label: "Superset",
          description:
            "Every expected value must appear in the output (extra output values are OK).",
        },
      ]}
      bind:value={properties.mode}
      hide_label
    />
  </FormSection>

  <OutputValueField
    id_prefix="set_check"
    bind:value={properties.value_expression}
  />
</div>
