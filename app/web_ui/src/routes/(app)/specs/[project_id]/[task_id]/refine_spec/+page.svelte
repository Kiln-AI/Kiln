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
  import { getStoredReviewedExamples } from "../spec_reviewed_examples_store"
  import { load_task } from "$lib/stores"
  import { client } from "$lib/api_client"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_error: KilnError | null = null
  let spec_loading = true

  let name = ""

  // Current/original values (read-only)
  let current_property_values: Record<string, string | null> = {}

  // Suggested values (editable)
  let suggested_property_values: Record<string, string | null> = {}

  // Original suggested values (before user edits, for Restore Suggestion functionality)
  let original_suggested_property_values: Record<string, string | null> = {}

  // Track which fields have AI-generated suggestions (for badge display)
  let ai_suggested_fields: Set<string> = new Set()
  $: ai_suggested_fields_size = ai_suggested_fields.size

  let disabledKeys: Set<string> = new Set(["tool_function_name"])

  // Restore a field to its original AI-suggested value (undo user edits)
  function restoreSuggestion(key: string) {
    suggested_property_values[key] = original_suggested_property_values[key]
    suggested_property_values = suggested_property_values // trigger reactivity
  }

  function resetToOriginal(key: string) {
    suggested_property_values[key] = current_property_values[key]
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

        current_property_values = { ...formData.property_values }

        evaluate_full_trace = formData.evaluate_full_trace

        // If we have review feedback, call the refine API
        const reviewed_examples = getStoredReviewedExamples(project_id, task_id)
        if (reviewed_examples && reviewed_examples.length > 0) {
          // Load the task to get instruction and schemas
          const task = await load_task(project_id, task_id)
          if (!task) {
            throw new Error("Failed to load task")
          }

          // Build spec info
          const spec_fields: Record<string, string> = {}
          const spec_field_current_values: Record<string, string> = {}

          for (const field of field_configs) {
            spec_fields[field.key] = field.description
            spec_field_current_values[field.key] =
              current_property_values[field.key] || ""
          }

          // Build task info
          const task_info = {
            task_prompt: task.instruction || "",
            few_shot_examples: null,
          }

          const examples_with_feedback = reviewed_examples
            .filter((example) => example.feedback !== null)
            .map((example) => ({
              user_rating_exhibits_issue_correct:
                example.model_says_meets_spec === example.user_says_meets_spec,
              user_feedback: example.feedback,
              input: example.input,
              output: example.output,
              exhibits_issue: !example.user_says_meets_spec,
            }))

          if (examples_with_feedback.length === 0) {
            // This shouldn't happen, but just in case
            throw new Error(
              "No valid reviewed examples with feedback to refine spec",
            )
          }

          // Call the refine API
          const { data, error } = await client.POST(
            "/api/copilot/refine_spec",
            {
              body: {
                task_prompt_with_few_shot: task.instruction || "",
                task_input_schema: task.input_json_schema
                  ? JSON.stringify(task.input_json_schema)
                  : "",
                task_output_schema: task.output_json_schema
                  ? JSON.stringify(task.output_json_schema)
                  : "",
                task_info,
                spec: {
                  spec_fields,
                  spec_field_current_values,
                },
                examples_with_feedback,
              },
            },
          )

          const { data, error } = {
            data: {
              new_proposed_spec_edits: {
                base_instruction: {
                  proposed_edit: "New base instruction",
                },
                correct_behaviour_examples: {
                  proposed_edit: "New correct behaviour examples",
                },
              },
            },
            error: null,
          }

          if (error) {
            throw error
          }

          if (!data) {
            throw new Error("Failed to refine spec")
          }

          // Build suggested_property_values: use original values, but override with AI suggestions where available
          suggested_property_values = { ...current_property_values }
          if (data.new_proposed_spec_edits) {
            for (const [field_key, edit] of Object.entries(
              data.new_proposed_spec_edits,
            )) {
              suggested_property_values[field_key] = edit.proposed_edit
              ai_suggested_fields.add(field_key)
            }
            // Create new Set to trigger reactivity
            ai_suggested_fields = new Set(ai_suggested_fields)
          }
          original_suggested_property_values = { ...suggested_property_values }
        }

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

      const use_kiln_copilot = true
      const spec_id = await createSpec(
        project_id,
        task_id,
        name,
        spec_type,
        suggested_property_values,
        use_kiln_copilot,
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

<div
  class={!spec_loading && !spec_error && ai_suggested_fields_size > 0
    ? "full-width"
    : "max-w-[900px]"}
>
  <AppPage
    title="Copilot: Review Suggested Refinements"
    subtitle={spec_loading
      ? undefined
      : "Polish your spec to be analyzed further."}
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/evaluations"
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
        <div class="flex flex-col">
          <div class="font-medium">Refine your Spec</div>
          <div class="font-light text-gray-500 text-sm">
            {ai_suggested_fields_size === 0
              ? `Kiln has not suggested any refinements, your spec is ready to be created. Edit your spec if you would like to manually refine it further.`
              : `Kiln has suggested ${ai_suggested_fields_size} refinement${ai_suggested_fields_size === 1 ? "" : "s"}. Review and optionally edit your refined spec before continuing to review new examples.`}
          </div>
        </div>
        <div class="border-t" />
        {#if ai_suggested_fields_size > 0}
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
                inline_action={suggested_property_values[field.key] !==
                  original_suggested_property_values[field.key] &&
                ai_suggested_fields.has(field.key)
                  ? {
                      label: "Restore Suggestion",
                      handler: () => restoreSuggestion(field.key),
                    }
                  : suggested_property_values[field.key] !==
                      current_property_values[field.key]
                    ? {
                        label: "Reset",
                        handler: () => resetToOriginal(field.key),
                      }
                    : undefined}
              >
                <svelte:fragment slot="label_suffix">
                  {#if !disabledKeys.has(field.key)}
                    {#if ai_suggested_fields.has(field.key)}
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
            value={name}
          />

          <!-- Field Rows -->
          {#each field_configs as field (field.key)}
            <FormElement
              label={field.label}
              id={`current_${field.key}`}
              inputType="textarea"
              description={field.description}
              height={bumpHeight(field.key, field.height)}
              value={current_property_values[field.key] ?? ""}
              optional={!field.required}
            />
          {/each}
        {/if}
        {#if !has_refinements && ai_suggested_fields_size > 0}
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
            on:click={create_spec}
            >Save Refined Spec without Further Review</button
          >
        </div>
      {/if}
    {/if}
  </AppPage>
</div>
