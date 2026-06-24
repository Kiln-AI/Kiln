<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"

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
</script>

<div class="flex flex-col gap-4">
  <FormElement
    id="contains_mode"
    label="Mode"
    description="Whether the output must contain or must not contain the value."
    inputType="select"
    bind:value={properties.mode}
    select_options={[
      ["must_contain", "Must Contain"],
      ["must_not_contain", "Must Not Contain"],
    ]}
  />

  <FormElement
    id="contains_source"
    label="Match Source"
    description="Choose what value to search for in the output."
    inputType="select"
    bind:value={source}
    select_options={[
      ["substring", "Fixed Substring"],
      ["reference_key", "Reference Data Key"],
    ]}
    on_select={() => {
      if (source === "substring") {
        properties.reference_key = null
      } else {
        properties.substring = null
      }
    }}
  />

  {#if source === "substring"}
    <FormElement
      id="contains_substring"
      label="Substring"
      description="The substring to search for in the output."
      inputType="input"
      bind:value={properties.substring}
    />
  {:else}
    <FormElement
      id="contains_reference_key"
      label="Reference Key"
      description="The key in the reference data whose value to search for in the output."
      inputType="input"
      bind:value={properties.reference_key}
    />
  {/if}

  <FormElement
    id="contains_value_expression"
    label="Value Expression"
    description="Optional Jinja2 expression to extract a value from the eval input before searching. Leave blank to use the full model output."
    inputType="input"
    optional={true}
    bind:value={properties.value_expression}
  />

  <FormElement
    id="contains_case_sensitive"
    label="Case Sensitive"
    inputType="checkbox"
    bind:value={properties.case_sensitive}
  />
</div>
