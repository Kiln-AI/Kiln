<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"

  export let properties: components["schemas"]["PatternMatchProperties"] = {
    type: "pattern_match",
    pattern: "",
    mode: "must_match",
    value_expression: null,
  }

  export function getProperties(): components["schemas"]["PatternMatchProperties"] {
    return properties
  }
</script>

<div class="flex flex-col gap-4">
  <FormElement
    id="pattern_match_pattern"
    label="Regular Expression"
    description="The regex pattern to test against the output."
    inputType="input"
    bind:value={properties.pattern}
  />

  <FormElement
    id="pattern_match_mode"
    label="Mode"
    description="Whether the output must match or must not match the pattern."
    inputType="select"
    bind:value={properties.mode}
    select_options={[
      ["must_match", "Must Match"],
      ["must_not_match", "Must Not Match"],
    ]}
  />

  <FormElement
    id="pattern_match_value_expression"
    label="Value Expression"
    description="Optional JSONPath or expression to extract the value from the output before matching."
    inputType="input"
    optional={true}
    bind:value={properties.value_expression}
  />
</div>
