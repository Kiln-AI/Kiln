<svelte:options accessors />

<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormSection from "./form_section.svelte"
  import {
    parseValue,
    emitValue,
    JINJA_EXAMPLES,
    type OutputMode,
  } from "./output_value_helpers"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let value: string | null = null
  export let id_prefix: string
  export let extra_description: string = ""

  let mode: OutputMode = "final_message"
  let customText: string = ""

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

  // Guard to prevent reactive loops: tracks the value we last set.
  let lastSetValue: string | null | undefined = undefined

  // Track previous mode to detect user-driven changes.
  let modePrev: OutputMode = mode

  // Track previous customText to detect user-driven changes.
  let customTextPrev: string = customText

  function syncFromValue() {
    const parsed = parseValue(value)
    mode = parsed.mode
    modePrev = parsed.mode
    customText = parsed.customText
    customTextPrev = parsed.customText
    lastSetValue = value
  }

  // Initialize
  syncFromValue()

  // When `value` changes externally, re-parse into mode/customText.
  // Skip if the change came from our own emit (lastSetValue matches).
  $: if (value !== lastSetValue) {
    syncFromValue()
  }

  function emitFromUI() {
    const newVal = emitValue({ mode, customText })
    lastSetValue = newVal
    value = newVal
  }

  function onModeChange() {
    // When switching into custom mode, prefill with the current concrete expression
    if (mode === "custom") {
      if (!customText.trim()) {
        // Use the previous concrete value as starting base
        const previous = lastSetValue
        if (previous === "trace") {
          customText = "trace"
        } else {
          customText = "final_message"
        }
        customTextPrev = customText
      }
    }
    emitFromUI()
  }

  // Reactive emit when mode changes via dropdown binding.
  $: if (mode !== modePrev) {
    modePrev = mode
    onModeChange()
  }

  // Reactive emit when customText changes via text input binding.
  $: if (customText !== customTextPrev) {
    customTextPrev = customText
    emitFromUI()
  }

  function selectExample(expression: string) {
    mode = "custom"
    customText = expression
    customTextPrev = expression
    emitFromUI()
    examplesDialog.close()
  }
</script>

<FormSection
  title="Value to Compare"
  subtitle="Choose which part of the model output to evaluate."
  testid="output-value-section"
>
  <FormElement
    id="{id_prefix}_output_source"
    label="Value to Compare"
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
        optional
        bind:value={customText}
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
