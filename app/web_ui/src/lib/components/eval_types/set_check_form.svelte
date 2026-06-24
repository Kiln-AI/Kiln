<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
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

  let expected_set_tags: string[] = properties.expected_set ?? []
  $: properties.expected_set = expected_set_tags
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

  <div role="group" aria-labelledby="set_check_source_label">
    <span id="set_check_source_label" class="text-sm font-medium"
      >Expected Set Source</span
    >
    <p class="text-xs text-gray-500 pb-1">
      Choose where the expected set values come from.
    </p>
    <div class="flex flex-col gap-3 pl-1">
      <label class="flex items-start gap-2 cursor-pointer">
        <input
          type="radio"
          name="set_check_source"
          class="radio radio-sm mt-0.5"
          value="expected_set"
          bind:group={source}
          on:change={() => {
            properties.reference_key = null
          }}
        />
        <span class="flex flex-col gap-1 flex-1">
          <span class="text-sm">Fixed Expected Set</span>
          <div class="pt-0.5">
            <TagInput
              id="set_check_expected_set"
              bind:tags={expected_set_tags}
              placeholder="Type a value and press Enter"
              disabled={source !== "expected_set"}
            />
            <p class="text-xs text-gray-500 pt-1">
              Add items by typing and pressing Enter or comma.
            </p>
          </div>
        </span>
      </label>
      <label class="flex items-start gap-2 cursor-pointer">
        <input
          type="radio"
          name="set_check_source"
          class="radio radio-sm mt-0.5"
          value="reference_key"
          bind:group={source}
          on:change={() => {
            properties.expected_set = null
            expected_set_tags = []
          }}
        />
        <span class="flex flex-col gap-1 flex-1">
          <span class="text-sm">Reference Data Key</span>
          <p class="text-xs text-gray-500">
            The key in the reference data containing the expected set.
          </p>
          <FormElement
            id="set_check_reference_key"
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
    id="set_check_value_expression"
    label="Value Expression"
    description="Optional Jinja2 expression to extract a value from the eval input before comparison. Leave blank to use the full model output."
    inputType="input"
    optional={true}
    bind:value={properties.value_expression}
  />
</div>
