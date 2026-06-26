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
  <FormSection title="Expected Substring" testid="contains-expected-section">
    <FormElement
      id="contains_source"
      inputType="radio"
      radio_options={[
        {
          value: "substring",
          label: "Fixed value",
          description: "Enter the text to search for in the output.",
        },
        {
          value: "reference_key",
          label: "From reference data",
          description:
            "Look up the search text from your dataset's reference fields.",
        },
      ]}
      bind:value={source}
      on_radio_change={on_source_change}
      hide_label
    />

    {#if source === "substring"}
      <div class="ml-4 border-l border-base-300 pl-4">
        <FormElement
          id="contains_substring"
          label="Value"
          inputType="input"
          placeholder="e.g. success"
          bind:value={properties.substring}
        />
      </div>
    {:else}
      <div class="ml-4 border-l border-base-300 pl-4">
        <FormElement
          id="contains_reference_key"
          label="Reference Data Field"
          inputType="input"
          placeholder="e.g. expected_keyword"
          description="A field in the reference data to compare output to, example: `user.expected_status`"
          info_description="Extract a value from reference data object. For example, use `user.email` to extract the email field from a JSON response. Uses Jinja extractor syntax."
          bind:value={properties.reference_key}
        />
      </div>
    {/if}
  </FormSection>

  <FormSection title="Match Mode" testid="contains-mode-section">
    <FormElement
      id="contains_mode"
      inputType="radio"
      radio_options={[
        {
          value: "must_contain",
          label: "Must contain",
          description: "The output must contain the value to pass.",
        },
        {
          value: "must_not_contain",
          label: "Must not contain",
          description: "The output must NOT contain the value to pass.",
        },
      ]}
      bind:value={properties.mode}
      hide_label
    />
  </FormSection>

  <FormSection title="Comparison Options" testid="contains-options-section">
    <FormElement
      id="contains_case_sensitive"
      label="Case Sensitive"
      inputType="checkbox"
      bind:value={properties.case_sensitive}
    />
  </FormSection>

  <OutputValueField
    id_prefix="contains"
    bind:value={properties.value_expression}
  />
</div>
