<svelte:options accessors />

<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormSection from "./form_section.svelte"
  import {
    parseValue,
    JINJA_EXAMPLES,
    type OutputMode,
  } from "./output_value_helpers"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let value: string | null = null
  export let id_prefix: string
  export let extra_description: string = ""

  // Two genuinely independent state variables:
  // 1. The dropdown/radio selection
  let mode: OutputMode = "final_message"
  // 2. The custom Jinja expression text (only meaningful when mode === "custom")
  let customJinja: string = ""

  let examplesDialog: Dialog

  const modeOptions: OptionGroup[] = [
    {
      options: [
        {
          value: "final_message",
          label: "Final Message",
          description: "Entire final message",
        },
        {
          value: "trace",
          label: "Entire Trace",
          description: "Entire trace in JSON",
        },
        {
          value: "custom",
          label: "Custom (Jinja)",
          description: "Build a custom expression from Jinja syntax.",
        },
      ],
    },
  ]

  const baseJinjaDescription =
    "Extract parts of the message or trace, using Jinja syntax."
  $: fullJinjaDescription = extra_description
    ? `${baseJinjaDescription} ${extra_description}`
    : baseJinjaDescription

  // Derive the effective value reactively from the two state vars.
  // This is NOT stored — it is computed on every change.
  $: derivedValue =
    mode === "final_message"
      ? "final_message"
      : mode === "trace"
        ? "trace"
        : customJinja.trim() || null

  // Guard to prevent reactive loops when we write to `value`.
  let lastEmittedValue: string | null = null

  // Sync: parse an incoming `value` prop into the two state vars.
  function syncFromValue() {
    const parsed = parseValue(value)
    mode = parsed.mode
    customJinja = parsed.customText
    lastEmittedValue = value
  }

  // Initialize from the prop.
  syncFromValue()

  // When `value` changes externally, re-parse into mode/customJinja.
  // Skip if the change came from our own reactive emit.
  $: if (value !== lastEmittedValue) {
    syncFromValue()
  }

  // Emit the derived value to the parent whenever it changes.
  $: {
    if (derivedValue !== lastEmittedValue) {
      lastEmittedValue = derivedValue
      value = derivedValue
    }
  }

  function selectExample(expression: string) {
    mode = "custom"
    customJinja = expression
    examplesDialog.close()
  }
</script>

<FormSection
  title="Output to Check"
  subtitle="Which part of the model's output to compare against the expected value."
  testid="output-value-section"
>
  <FormElement
    id="{id_prefix}_output_source"
    label="Output to Check"
    inputType="fancy_select"
    fancy_select_options={modeOptions}
    bind:value={mode}
    hide_label
  />

  {#if mode === "custom"}
    <div class="ml-4 border-l border-base-300 pl-4">
      <FormElement
        id="{id_prefix}_value_expression"
        label="Jinja Expression"
        description={fullJinjaDescription}
        inputType="input"
        placeholder="(final_message | fromjson).user.status"
        bind:value={customJinja}
        inline_action={{
          handler: () => examplesDialog.show(),
          label: "See Examples",
        }}
      />
    </div>
  {/if}
</FormSection>

<Dialog
  bind:this={examplesDialog}
  title="Jinja Expression Examples"
  subtitle="Examples of extracting data from final_message and trace using Jinja."
>
  <div class="flex flex-col -mx-2">
    {#each JINJA_EXAMPLES as example}
      <button
        type="button"
        class="flex flex-col gap-1 px-3 py-2.5 rounded-lg hover:bg-base-200 transition-colors text-left cursor-pointer"
        on:click={() => selectExample(example.expression)}
      >
        <span class="text-sm font-medium">{example.label}</span>
        <code
          class="text-xs font-mono bg-base-200 text-gray-500 px-2 py-0.5 rounded w-fit"
          >{example.expression}</code
        >
      </button>
    {/each}
  </div>
</Dialog>
