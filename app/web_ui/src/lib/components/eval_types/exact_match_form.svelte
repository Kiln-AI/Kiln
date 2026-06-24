<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"

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
</script>

<div class="flex flex-col gap-4">
  <div role="group" aria-labelledby="exact_match_source_label">
    <span id="exact_match_source_label" class="text-sm font-medium"
      >Match Source</span
    >
    <p class="text-xs text-gray-500 pb-1">
      Choose what value to compare the output against.
    </p>
    <div class="flex flex-col gap-3 pl-1">
      <label class="flex items-start gap-2 cursor-pointer">
        <input
          type="radio"
          name="exact_match_source"
          class="radio radio-sm mt-0.5"
          value="expected_value"
          bind:group={source}
          on:change={() => {
            properties.reference_key = null
          }}
        />
        <span class="flex flex-col gap-1 flex-1">
          <span class="text-sm">Fixed Expected Value</span>
          <p class="text-xs text-gray-500">
            The exact value the output must match.
          </p>
          <FormElement
            id="exact_match_expected_value"
            label="Expected Value"
            hide_label={true}
            aria_label="Expected Value"
            inputType="input"
            bind:value={properties.expected_value}
            disabled={source !== "expected_value"}
          />
        </span>
      </label>
      <label class="flex items-start gap-2 cursor-pointer">
        <input
          type="radio"
          name="exact_match_source"
          class="radio radio-sm mt-0.5"
          value="reference_key"
          bind:group={source}
          on:change={() => {
            properties.expected_value = null
          }}
        />
        <span class="flex flex-col gap-1 flex-1">
          <span class="text-sm">Reference Data Key</span>
          <p class="text-xs text-gray-500">
            The key in the reference data whose value the output must match.
          </p>
          <FormElement
            id="exact_match_reference_key"
            label="Reference Key"
            hide_label={true}
            aria_label="Reference Key"
            inputType="input"
            bind:value={properties.reference_key}
            disabled={source !== "reference_key"}
          />
        </span>
      </label>
    </div>
  </div>

  <FormElement
    id="exact_match_value_expression"
    label="Value Expression"
    description="Optional Jinja2 expression to extract a value from the eval input before comparison. Leave blank to use the full model output."
    inputType="input"
    optional={true}
    bind:value={properties.value_expression}
  />

  <FormElement
    id="exact_match_case_sensitive"
    label="Case Sensitive"
    inputType="checkbox"
    bind:value={properties.case_sensitive}
  />
</div>
