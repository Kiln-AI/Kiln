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

  let regex_error: string | null = null
  let pattern_touched = false

  function on_pattern_blur() {
    pattern_touched = true
    validate_regex()
  }

  function validate_regex() {
    if (!properties.pattern) {
      regex_error = null
      return
    }
    try {
      new RegExp(properties.pattern)
      regex_error = null
    } catch (e) {
      regex_error = `Invalid regex: ${e instanceof SyntaxError ? e.message : String(e)}`
    }
  }

  $: if (pattern_touched && properties.pattern !== undefined) {
    validate_regex()
  }

  export function validate(): string | null {
    if (!properties.pattern) {
      return "Regular expression is required."
    }
    try {
      new RegExp(properties.pattern)
    } catch {
      return "Invalid regular expression pattern."
    }
    return null
  }
</script>

<div class="flex flex-col gap-4">
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div on:blur={on_pattern_blur}>
    <FormElement
      id="pattern_match_pattern"
      label="Regular Expression"
      description="The regex pattern to test against the output."
      inputType="input"
      bind:value={properties.pattern}
      error_message={regex_error}
    />
  </div>

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
    description="Optional Jinja2 expression to extract a value from the eval input before matching. Leave blank to use the full model output."
    inputType="input"
    optional={true}
    bind:value={properties.value_expression}
  />
</div>
