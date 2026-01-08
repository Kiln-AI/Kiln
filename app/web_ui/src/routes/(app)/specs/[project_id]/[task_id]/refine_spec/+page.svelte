<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import FormElement from "$lib/utils/form_element.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import {
    createSpec,
    navigateToReviewSpec,
    loadSpecFormData,
  } from "../spec_utils"
  import Warning from "$lib/ui/warning.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_error: KilnError | null = null
  let spec_loading = true

  let name = ""

  // Current values (read-only)
  let current_property_values: Record<string, string | null> = {}

  // Suggested values (editable)
  let suggested_property_values: Record<string, string | null> = {}

  // Original suggested values (before user edits, for Reset functionality)
  let original_suggested_property_values: Record<string, string | null> = {}

  // Track which fields have AI-generated suggestions (for badge display)
  let ai_suggested_fields: Set<string> = new Set()

  let disabledKeys: Set<string> = new Set(["tool_function_name"])

  // Reset a field to its original suggested value (undo user edits)
  function resetField(key: string) {
    suggested_property_values[key] = original_suggested_property_values[key]
    suggested_property_values = suggested_property_values // trigger reactivity
  }

  // Check if any refinements were made (refined values differ from original values)
  $: has_refinements = Object.keys(suggested_property_values).some(
    (key) => suggested_property_values[key] !== current_property_values[key],
  )

  // Advanced options
  let evaluate_full_trace = false

  let spec_type: SpecType = "desired_behaviour"

  // Get field configs for the current spec_type
  $: field_configs = spec_field_configs[spec_type] || []

  // Bump up textarea heights for two-column layout (except single-line fields)
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

  onMount(async () => {
    await load_spec_data()
  })

  async function load_spec_data() {
    try {
      spec_loading = true
      spec_error = null

      const formData = loadSpecFormData(project_id, task_id)

      if (formData) {
        spec_type = formData.spec_type

        name = formData.name

        // Initialize current, suggested, and original suggested with the same values (temporary)
        current_property_values = { ...formData.property_values }
        suggested_property_values = { ...formData.property_values }
        original_suggested_property_values = { ...formData.property_values }

        evaluate_full_trace = formData.evaluate_full_trace

        // Don't clear the stored data - keep it for back navigation
        // It will be cleared when the spec is successfully created
      } else {
        // No form data found - redirect back to specs list
        // This happens when user navigates back after creating a spec
        goto(`/specs/${project_id}/${task_id}`)
        return
      }
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      spec_loading = false
    }
  }

  let submit_error: KilnError | null = null
  let submitting = false
  let complete = false
  async function analyze_spec() {
    try {
      submit_error = null
      submitting = true

      // Validate required fields
      for (const field of field_configs) {
        if (field.required) {
          const value = suggested_property_values[field.key]
          if (!value || !value.trim()) {
            throw createKilnError(`${field.label} is required`)
          }
        }
      }

      // Reset submitting state so button doesn't show spinner
      submitting = false

      // Set complete to true so the warn before unload doesn't show when navigating to review_spec
      complete = true

      // Navigate to review_spec page
      await navigateToReviewSpec(
        project_id,
        task_id,
        name,
        spec_type,
        suggested_property_values,
        evaluate_full_trace,
      )
    } catch (error) {
      submit_error = createKilnError(error)
      submitting = false
    }
  }

  async function create_spec() {
    try {
      submit_error = null
      submitting = true

      // Validate required fields
      for (const field of field_configs) {
        if (field.required) {
          const value = suggested_property_values[field.key]
          if (!value || !value.trim()) {
            throw createKilnError(`${field.label} is required`)
          }
        }
      }

      const spec_id = await createSpec(
        project_id,
        task_id,
        name,
        spec_type,
        suggested_property_values,
        evaluate_full_trace,
      )

      complete = true
      // Replace history so browser back goes to templates
      goto(`/specs/${project_id}/${task_id}/${spec_id}`, { replaceState: true })
    } catch (error) {
      submit_error = createKilnError(error)
    } finally {
      submitting = false
    }
  }
</script>

<AppPage
  title="Refine Spec"
  subtitle="Refine your spec so it correctly captures your goal"
  breadcrumbs={[
    {
      label: "Specs & Evals",
      href: `/specs/${project_id}/${task_id}`,
    },
    {
      label: "Spec Templates",
      href: `/specs/${project_id}/${task_id}/select_template`,
    },
  ]}
>
  {#if spec_loading}
    <div class="flex justify-center items-center h-full min-h-[200px]">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if spec_error}
    <div class="text-error text-sm">
      {spec_error.getMessage() || "An unknown error occurred"}
    </div>
  {:else}
    <FormContainer
      submit_label={has_refinements ? "Next" : "Create Spec"}
      on:submit={has_refinements ? analyze_spec : create_spec}
      bind:error={submit_error}
      bind:submitting
      warn_before_unload={!complete}
      compact_button={true}
    >
      <!-- Column Headers -->
      <div class="grid grid-cols-2 gap-8 mb-4">
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
            disabled={true}
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
            value={current_property_values[field.key] ?? ""}
            optional={!field.required}
          />
          <FormElement
            label={field.label}
            id={`suggested_${field.key}`}
            inputType="textarea"
            description={field.description}
            disabled={disabledKeys.has(field.key)}
            height={bumpHeight(field.key, field.height)}
            bind:value={suggested_property_values[field.key]}
            optional={!field.required}
            inline_action={disabledKeys.has(field.key)
              ? undefined
              : { label: "Reset", handler: () => resetField(field.key) }}
          >
            <svelte:fragment slot="label_suffix">
              {#if !disabledKeys.has(field.key)}
                {#if !ai_suggested_fields.has(field.key)}
                  <span
                    class="badge badge-success badge-outline badge-sm gap-1 ml-2"
                  >
                    No change suggested
                  </span>
                {:else}
                  <span
                    class="badge badge-warning badge-outline badge-sm gap-1 ml-2"
                  >
                    Refinement suggested
                  </span>
                {/if}
              {/if}
            </svelte:fragment>
          </FormElement>
        </div>
      {/each}
      {#if !has_refinements}
        <div class="flex justify-end">
          <Warning
            warning_color="success"
            warning_icon="check"
            warning_message="No refinements made. Your spec is ready to be created."
          />
        </div>
      {/if}
    </FormContainer>
    {#if has_refinements}
      <div class="flex flex-row gap-1 mt-2 justify-end">
        <span class="text-xs text-gray-500">or</span>
        <button
          class="link underline text-xs text-gray-500"
          on:click={create_spec}>Skip Review and Create Spec</button
        >
      </div>
    {/if}
  {/if}
</AppPage>
