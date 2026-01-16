<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { FieldConfig } from "../select_template/spec_templates"

  export let name: string
  export let property_values: Record<string, string | null>
  export let initial_property_values: Record<string, string | null>
  export let evaluate_full_trace: boolean
  export let field_configs: FieldConfig[]
  export let copilot_enabled: boolean
  export let show_advanced_options: boolean
  export let full_trace_disabled: boolean
  export let error: KilnError | null
  export let submitting: boolean
  export let warn_before_unload: boolean

  const dispatch = createEventDispatcher<{
    analyze_with_copilot: void
    create_without_copilot: void
  }>()

  function reset_field(key: string) {
    property_values[key] = initial_property_values[key] ?? null
  }

  function has_form_changes(): boolean {
    for (const key of Object.keys(property_values)) {
      if (property_values[key] !== initial_property_values[key]) return true
    }
    return false
  }

  $: computed_warn_before_unload = warn_before_unload && has_form_changes()

  function handle_submit() {
    if (copilot_enabled) {
      dispatch("analyze_with_copilot")
    } else {
      dispatch("create_without_copilot")
    }
  }
</script>

<FormContainer
  submit_label={copilot_enabled ? "Analyze with Copilot" : "Create Spec"}
  on:submit={handle_submit}
  bind:error
  bind:submitting
  compact_button={true}
  warn_before_unload={computed_warn_before_unload}
>
  <FormElement
    label="Spec Name"
    description="A short name for your own reference."
    id="spec_name"
    bind:value={name}
  />

  {#each field_configs as field (field.key)}
    <FormElement
      label={field.label}
      id={field.key}
      inputType="textarea"
      disabled={field.disabled || false}
      description={field.description}
      info_description={field.info_description}
      height={field.height || "base"}
      bind:value={property_values[field.key]}
      optional={!field.required}
      inline_action={initial_property_values[field.key] &&
      property_values[field.key] !== initial_property_values[field.key]
        ? {
            handler: () => reset_field(field.key),
            label: "Reset",
          }
        : undefined}
    />
  {/each}

  {#if show_advanced_options}
    <Collapse title="Advanced Options">
      <FormElement
        label="Include conversation history"
        id="evaluate_full_trace"
        inputType="checkbox"
        bind:value={evaluate_full_trace}
        disabled={full_trace_disabled}
        description="When enabled, this spec will be evaluated on the full conversation history including intermediate steps and tool calls. When disabled, only the final answer is evaluated."
        info_description={full_trace_disabled
          ? "Tool use specs always evaluate the full conversation history to analyze tool calls."
          : "Enable this for specs that need to evaluate reasoning steps, tool usage, or intermediate outputs."}
      />
    </Collapse>
  {/if}
</FormContainer>

{#if copilot_enabled}
  <div class="flex flex-row gap-1 mt-4 justify-end">
    <span class="text-sm text-gray-500">or</span>
    <button
      class="link underline text-sm text-gray-500"
      disabled={submitting}
      on:click={() => dispatch("create_without_copilot")}
    >
      Create without Copilot
    </button>
  </div>
{/if}
