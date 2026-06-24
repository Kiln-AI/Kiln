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

  <div role="group" aria-labelledby="contains_source_label">
    <span id="contains_source_label" class="text-sm font-medium"
      >Search String Source</span
    >
    <p class="text-xs text-gray-500 pb-1">
      Choose what value to search for in the output.
    </p>
    <div class="flex flex-col gap-3 pl-1">
      <label class="flex items-start gap-2 cursor-pointer">
        <input
          type="radio"
          name="contains_source"
          class="radio radio-sm mt-0.5"
          value="substring"
          bind:group={source}
          on:change={() => {
            properties.reference_key = null
          }}
        />
        <span class="flex flex-col gap-1 flex-1">
          <span class="text-sm">Fixed Substring</span>
          <p class="text-xs text-gray-500">
            The substring to search for in the output.
          </p>
          <FormElement
            id="contains_substring"
            label="Substring"
            hide_label={true}
            aria_label="Substring"
            inputType="input"
            bind:value={properties.substring}
            disabled={source !== "substring"}
          />
        </span>
      </label>
      <label class="flex items-start gap-2 cursor-pointer">
        <input
          type="radio"
          name="contains_source"
          class="radio radio-sm mt-0.5"
          value="reference_key"
          bind:group={source}
          on:change={() => {
            properties.substring = null
          }}
        />
        <span class="flex flex-col gap-1 flex-1">
          <span class="text-sm">Reference Data Key</span>
          <p class="text-xs text-gray-500">
            The key in the reference data whose value to search for in the
            output.
          </p>
          <FormElement
            id="contains_reference_key"
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
