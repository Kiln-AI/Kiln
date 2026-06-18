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

  // TODO(pre-ship 5.3): The "Reference Data Key" source option below lets users configure
  // exact_match to compare against reference_data, but in V2.0 no UI path populates
  // reference_data on EvalInputs — so this eval will always silently skip at runtime.
  // Before shipping to main: either wire reference_data population into the UI,
  // or remove the "reference_key" source option from this form.
  let source: "expected_value" | "reference_key" = properties.expected_value
    ? "expected_value"
    : properties.reference_key
      ? "reference_key"
      : "expected_value"
</script>

<div class="flex flex-col gap-4">
  <FormElement
    id="exact_match_source"
    label="Match Source"
    description="Choose what value to compare the output against."
    inputType="select"
    bind:value={source}
    select_options={[
      ["expected_value", "Fixed Expected Value"],
      ["reference_key", "Reference Data Key"],
    ]}
    on_select={() => {
      if (source === "expected_value") {
        properties.reference_key = null
      } else {
        properties.expected_value = null
      }
    }}
  />

  {#if source === "expected_value"}
    <FormElement
      id="exact_match_expected_value"
      label="Expected Value"
      description="The exact value the output must match."
      inputType="input"
      bind:value={properties.expected_value}
    />
  {:else}
    <FormElement
      id="exact_match_reference_key"
      label="Reference Key"
      description="The key in the reference data whose value the output must match."
      inputType="input"
      bind:value={properties.reference_key}
    />
  {/if}

  <FormElement
    id="exact_match_value_expression"
    label="Value Expression"
    description="Optional JSONPath or expression to extract the value from the output before comparing."
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
