<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { FieldConfig } from "../select_template/spec_templates"
  import { filename_string_short_validator } from "$lib/utils/input_validators"

  export let name: string
  export let original_property_values: Record<string, string | null>
  export let refined_property_values: Record<string, string | null>
  export let starting_refined_property_values: Record<string, string | null>
  export let suggested_fields: Set<string>
  export let field_configs: FieldConfig[]
  export let error: KilnError | null
  export let submitting: boolean
  export let warn_before_unload: boolean

  let form_container: FormContainer

  const dispatch = createEventDispatcher<{
    analyze_refined: void
    create_spec: void
    create_spec_secondary: void
  }>()

  let disabledKeys: Set<string> = new Set(["tool_function_name"])

  $: has_suggested_refinements = suggested_fields.size > 0

  // Check if any refinements were made from the original
  $: has_refinements = Object.keys(refined_property_values).some(
    (key) => refined_property_values[key] !== original_property_values[key],
  )

  function restoreSuggestion(key: string) {
    refined_property_values[key] = starting_refined_property_values[key]
    refined_property_values = refined_property_values
  }

  function resetToOriginal(key: string) {
    refined_property_values[key] = original_property_values[key]
    refined_property_values = refined_property_values
  }

  // Bump up textarea heights for two-column layout
  type TextareaHeight = "base" | "medium" | "large" | "xl"
  const singleLineFields = new Set(["tool_function_name"])
  function bumpHeight(
    key: string,
    height: TextareaHeight | undefined,
  ): TextareaHeight {
    if (singleLineFields.has(key)) {
      return height || "base"
    }
    const heightMap: Record<TextareaHeight, TextareaHeight> = {
      base: "medium",
      medium: "large",
      large: "xl",
      xl: "xl",
    }
    return heightMap[height || "base"]
  }

  $: submit_label = has_refinements ? "Analyze Refined Spec" : "Create Spec"

  function handle_submit() {
    if (has_refinements) {
      dispatch("analyze_refined")
    } else {
      dispatch("create_spec")
    }
  }

  async function handle_secondary_click() {
    if (await form_container.validate_only()) {
      dispatch("create_spec_secondary")
    }
  }
</script>

<FormContainer
  bind:this={form_container}
  {submit_label}
  on:submit={handle_submit}
  bind:error
  bind:submitting
  {warn_before_unload}
  compact_button={true}
>
  <div class="flex flex-col">
    <div class="font-medium">Refine your Spec</div>
    <div class="font-light text-gray-500 text-sm">
      {has_suggested_refinements
        ? `Kiln has suggested ${suggested_fields.size} refinement${suggested_fields.size === 1 ? "" : "s"}. Review and optionally edit your refined spec before continuing to review new examples.`
        : `Kiln has not suggested any refinements, your spec is ready to be created. Edit your spec if you would like to manually refine it further.`}
    </div>
  </div>
  <div class="border-t" />
  {#if has_suggested_refinements}
    <!-- Column Headers -->
    <div class="grid grid-cols-2 gap-8">
      <div class="text-xl font-bold">Original</div>
      <div class="text-xl font-bold">Refined</div>
    </div>

    <!-- Spec Name Row -->
    <div class="grid grid-cols-2 gap-8">
      <FormElement
        label="Spec Name"
        description="A short name for your own reference."
        id="current_spec_name"
        value={name}
        disabled={true}
      />
      <div>
        <FormElement
          label="Spec Name"
          description="A short name for your own reference."
          id="suggested_spec_name"
          bind:value={name}
          validator={filename_string_short_validator}
        />
      </div>
    </div>

    <!-- Field Rows -->
    {#each field_configs as field (field.key)}
      <div class="grid grid-cols-2 gap-8">
        <FormElement
          label={field.label}
          id={`current_${field.key}`}
          inputType="textarea"
          disabled={true}
          description={field.description}
          height={bumpHeight(field.key, field.height)}
          value={original_property_values[field.key] ?? ""}
          optional={!field.required}
          hide_optional_badge={true}
        />
        <FormElement
          label={field.label}
          id={`suggested_${field.key}`}
          inputType="textarea"
          description={field.description}
          disabled={disabledKeys.has(field.key)}
          height={bumpHeight(field.key, field.height)}
          bind:value={refined_property_values[field.key]}
          optional={!field.required}
          inline_action={refined_property_values[field.key] !==
            starting_refined_property_values[field.key] &&
          suggested_fields.has(field.key)
            ? {
                label: "Restore Suggestion",
                handler: () => restoreSuggestion(field.key),
              }
            : refined_property_values[field.key] !==
                original_property_values[field.key]
              ? {
                  label: "Reset",
                  handler: () => resetToOriginal(field.key),
                }
              : undefined}
        >
          <svelte:fragment slot="label_suffix">
            {#if !disabledKeys.has(field.key)}
              {#if suggested_fields.has(field.key)}
                <span
                  class="badge badge-primary badge-outline badge-sm gap-1 ml-2"
                >
                  Refinement Suggested
                </span>
              {/if}
            {/if}
          </svelte:fragment>
        </FormElement>
      </div>
    {/each}
  {:else}
    <!-- Spec Name Row -->
    <FormElement
      label="Spec Name"
      description="A short name for your own reference."
      id="current_spec_name"
      bind:value={name}
      validator={filename_string_short_validator}
    />

    <!-- Field Rows -->
    {#each field_configs as field (field.key)}
      <FormElement
        label={field.label}
        id={`current_${field.key}`}
        inputType="textarea"
        description={field.description}
        height={bumpHeight(field.key, field.height)}
        bind:value={refined_property_values[field.key]}
        optional={!field.required}
      />
    {/each}
  {/if}
  {#if !has_refinements && has_suggested_refinements}
    <div class="flex justify-end">
      <Warning
        warning_color="success"
        warning_icon="check"
        tight={true}
        warning_message="No changes made. Your spec is ready to be created."
      />
    </div>
  {/if}
</FormContainer>
{#if has_refinements}
  <div class="flex flex-row gap-1 mt-4 justify-end">
    <span class="text-sm text-gray-500">or</span>
    <button
      class="link underline text-sm text-gray-500"
      disabled={submitting}
      on:click={handle_secondary_click}
    >
      Save Refined Spec without Further Review
    </button>
  </div>
{/if}
