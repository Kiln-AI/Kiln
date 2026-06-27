<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import FormSection from "./form_section.svelte"
  import {
    parseValue,
    emitValue,
    type OutputSource,
  } from "./output_value_helpers"

  export let value: string | null = null
  export let id_prefix: string
  export let extra_description: string = ""

  // Internal UI state
  let source: OutputSource = "final_message"
  let selector: string = ""

  // Selector copy depends on the source: the final message is a string/JSON
  // object (field paths like `user.status`), while the trace is an
  // OpenAI-style list of messages (index paths like `[-1].content`).
  $: is_trace = source === "trace"

  $: base_description = is_trace
    ? "A field in the trace to evaluate, e.g. `[-1].content`. Leave blank to use the entire trace."
    : "A field in the message to evaluate, e.g. `user.status`. Leave blank to use the entire message."
  $: full_description = extra_description
    ? `${base_description} ${extra_description}`
    : base_description

  const selector_label = "Sub-field"

  $: selector_placeholder = is_trace ? "e.g. [-1].content" : "e.g. user.status"

  $: selector_info = is_trace
    ? "Extract a value from the conversation trace, which is a list of messages. For example, `[0].content` is the first message's content, or `[0].tool_calls[0].function.name` for a tool call. Uses Jinja extractor syntax."
    : "Extract a value from the model output. For example, use `user.email` to extract the email field from a JSON response. Uses Jinja extractor syntax."

  // Guard to prevent reactive loops: tracks the value we last set.
  let lastSetValue: string | null | undefined = undefined

  // Track previous selector to detect user-driven changes (not sync-driven).
  let selectorPrev: string = selector

  function syncFromValue() {
    const parsed = parseValue(value)
    source = parsed.source
    selector = parsed.selector
    selectorPrev = parsed.selector
    lastSetValue = value
  }

  // Initialize
  syncFromValue()

  // When `value` changes externally, re-parse into source/selector.
  // Skip if the change came from our own emit (lastSetValue matches).
  $: if (value !== lastSetValue) {
    syncFromValue()
  }

  function emitFromUI() {
    const newVal = emitValue({ source, selector })
    lastSetValue = newVal
    value = newVal
  }

  function on_source_change() {
    emitFromUI()
  }

  // Reactive emit when selector changes via text input binding.
  $: if (selector !== selectorPrev) {
    selectorPrev = selector
    emitFromUI()
  }
</script>

<FormSection
  title="Value to Check"
  subtitle="Choose which part of the model output to evaluate."
  testid="output-value-section"
>
  <FormElement
    id="{id_prefix}_output_source"
    inputType="radio"
    radio_options={[
      {
        value: "final_message",
        label: "Final Message",
        description: "The model's final output.",
      },
      {
        value: "trace",
        label: "Entire Trace",
        description: "The full conversation/tool-call trace.",
      },
    ]}
    bind:value={source}
    on_radio_change={on_source_change}
    hide_label
  />

  <div class="ml-4 border-l border-base-300 pl-4">
    <FormElement
      id="{id_prefix}_value_expression"
      label={selector_label}
      description={full_description}
      info_description={selector_info}
      inputType="input"
      optional={true}
      placeholder={selector_placeholder}
      bind:value={selector}
    />
  </div>
</FormSection>
