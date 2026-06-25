<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_parts/form_section.svelte"
  import OutputValueField from "./form_parts/output_value_field.svelte"

  export let properties: components["schemas"]["ContainsProperties"] = {
    type: "contains",
    case_sensitive: true,
    mode: "must_contain",
    value_expression: null,
    substring: null,
    reference_key: null,
  }

  export function getProperties(): components["schemas"]["ContainsProperties"] {
    return properties
  }

  export function validate(): string | null {
    if (source === "substring" && !properties.substring) {
      return "Substring is required."
    }
    if (source === "reference_key" && !properties.reference_key) {
      return "Reference key is required."
    }
    return null
  }

  let source: "substring" | "reference_key" = properties.reference_key
    ? "reference_key"
    : "substring"

  function on_source_change() {
    if (source === "substring") {
      properties.reference_key = null
    } else {
      properties.substring = null
    }
  }
</script>

<div class="flex flex-col gap-6">
  <FormSection
    title="Expected Substring"
    subtitle="Choose what value to search for in the output."
    testid="contains-expected-section"
  >
    <FormElement
      id="contains_source"
      inputType="radio"
      radio_options={[
        {
          value: "substring",
          label: "Fixed substring",
          description:
            "Specify the exact substring to search for in the output.",
        },
        {
          value: "reference_key",
          label: "Value from reference data",
          description:
            "Use a key from the reference data whose value to search for in the output.",
        },
      ]}
      bind:value={source}
      on_radio_change={on_source_change}
      hide_label
    />

    {#if source === "substring"}
      <FormElement
        id="contains_substring"
        label="Substring"
        inputType="input"
        bind:value={properties.substring}
      />
    {:else}
      <FormElement
        id="contains_reference_key"
        label="Reference Key"
        description="The key in the reference data whose value to search for."
        inputType="input"
        bind:value={properties.reference_key}
      />
    {/if}
  </FormSection>

  <FormSection
    title="Match Mode"
    subtitle="Choose whether the output should contain or not contain the value."
    testid="contains-mode-section"
  >
    <FormElement
      id="contains_mode"
      inputType="radio"
      radio_options={[
        {
          value: "must_contain",
          label: "Must contain",
          description: "The output must contain the substring to pass.",
        },
        {
          value: "must_not_contain",
          label: "Must not contain",
          description: "The output must NOT contain the substring to pass.",
        },
      ]}
      bind:value={properties.mode}
      hide_label
    />
  </FormSection>

  <OutputValueField
    id_prefix="contains"
    bind:value={properties.value_expression}
  >
    <FormElement
      id="contains_case_sensitive"
      label="Case Sensitive"
      inputType="checkbox"
      bind:value={properties.case_sensitive}
    />
  </OutputValueField>
</div>
