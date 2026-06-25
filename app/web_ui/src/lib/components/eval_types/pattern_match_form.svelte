<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_parts/form_section.svelte"
  import DisclosureRadioGroup from "./form_parts/disclosure_radio_group.svelte"
  import OutputValueField from "./form_parts/output_value_field.svelte"

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

<div class="flex flex-col gap-6">
  <FormSection
    title="Pattern"
    subtitle="Define the regular expression to test against the output."
    testid="pattern-match-pattern-section"
  >
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div on:blur={on_pattern_blur}>
      <FormElement
        id="pattern_match_pattern"
        label="Regular Expression"
        description="The regex pattern to test against the output. Example: ^hello.*world$"
        info_description="A regular expression (regex) is a pattern that describes a set of strings. Use it to check if the output matches a specific format or contains certain patterns."
        inputType="input"
        bind:value={properties.pattern}
        error_message={regex_error}
      />
    </div>
  </FormSection>

  <FormSection
    title="Match Mode"
    subtitle="Choose whether the output should match or not match the pattern."
    testid="pattern-match-mode-section"
  >
    <DisclosureRadioGroup
      name="pattern_match_mode"
      options={[
        {
          value: "must_match",
          label: "Must match",
          description: "The output must match the regular expression to pass.",
        },
        {
          value: "must_not_match",
          label: "Must not match",
          description:
            "The output must NOT match the regular expression to pass.",
        },
      ]}
      bind:selected={properties.mode}
    />
  </FormSection>

  <OutputValueField
    id_prefix="pattern_match"
    bind:value={properties.value_expression}
  />
</div>
