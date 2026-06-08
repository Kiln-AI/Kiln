<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"

  export let properties: components["schemas"]["SetCheckProperties"] = {
    type: "set_check",
    mode: "equal",
    value_expression: null,
    expected_set: [],
    reference_key: null,
  }

  export function getProperties(): components["schemas"]["SetCheckProperties"] {
    return properties
  }

  let source: "expected_set" | "reference_key" = properties.reference_key
    ? "reference_key"
    : "expected_set"

  let expected_set_text: string = (properties.expected_set ?? []).join("\n")

  $: properties.expected_set = expected_set_text
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
</script>

<div class="flex flex-col gap-4">
  <FormElement
    id="set_check_mode"
    label="Set Comparison Mode"
    description="How to compare the output set against the expected set."
    inputType="select"
    bind:value={properties.mode}
    select_options={[
      ["equal", "Equal (exact same elements)"],
      ["subset", "Subset (output is subset of expected)"],
      ["superset", "Superset (output is superset of expected)"],
    ]}
  />

  <FormElement
    id="set_check_source"
    label="Expected Set Source"
    description="Choose where the expected set values come from."
    inputType="select"
    bind:value={source}
    select_options={[
      ["expected_set", "Fixed Expected Set"],
      ["reference_key", "Reference Data Key"],
    ]}
    on_select={() => {
      if (source === "expected_set") {
        properties.reference_key = null
      } else {
        properties.expected_set = null
      }
    }}
  />

  {#if source === "expected_set"}
    <FormElement
      id="set_check_expected_set"
      label="Expected Set"
      description="One value per line. The output will be parsed and compared as a set."
      inputType="textarea"
      bind:value={expected_set_text}
    />
  {:else}
    <FormElement
      id="set_check_reference_key"
      label="Reference Key"
      description="The key in the reference data containing the expected set."
      inputType="input"
      bind:value={properties.reference_key}
    />
  {/if}

  <FormElement
    id="set_check_value_expression"
    label="Value Expression"
    description="Optional JSONPath or expression to extract the value from the output before comparison."
    inputType="input"
    optional={true}
    bind:value={properties.value_expression}
  />
</div>
