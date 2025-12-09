<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import { createSpec, navigateToReviewSpec } from "../spec_utils"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_error: KilnError | null = null
  let spec_loading = true

  // Current values (read-only)
  let current_name = ""
  let current_property_values: Record<string, string | null> = {}

  // Suggested values (editable)
  let suggested_property_values: Record<string, string | null> = {}

  // Track which fields have AI-generated suggestions (empty means no suggestion, use current value)
  let ai_suggested_fields: Set<string> = new Set()
  let disabledKeys: Set<string> = new Set(["tool_function_name"])

  // Check if a field has an AI suggestion
  function hasAiSuggestion(key: string): boolean {
    return ai_suggested_fields.has(key)
  }

  let spec_type: SpecType = "behaviour"

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

      const formDataKey = `spec_refine_${project_id}_${task_id}`
      const storedData = sessionStorage.getItem(formDataKey)

      if (storedData) {
        const formData = JSON.parse(storedData)
        spec_type = formData.spec_type || "behaviour"

        // Initialize both current and suggested with the same values
        current_name = formData.name || ""

        current_property_values = { ...formData.property_values }
        suggested_property_values = { ...formData.property_values }

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

  let analyze_dialog: Dialog | null = null
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

      // Show analyzing dialog
      analyze_dialog?.show()

      // Wait 2 seconds
      await new Promise((resolve) => setTimeout(resolve, 2000))

      // Navigate to review_spec page
      await navigateToReviewSpec(
        project_id,
        task_id,
        current_name,
        spec_type,
        suggested_property_values,
      )
    } catch (error) {
      submit_error = createKilnError(error)
      analyze_dialog?.hide()
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
        current_name,
        spec_type,
        suggested_property_values,
      )

      if (spec_id) {
        goto(`/specs/${project_id}/${task_id}/${spec_id}`)
      }
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
      label: "Specs",
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
      submit_label="Next"
      on:submit={analyze_spec}
      bind:error={submit_error}
      bind:submitting
    >
      <!-- Column Headers -->
      <div class="grid grid-cols-2 gap-8 mb-4">
        <div class="text-xl font-bold">Current</div>
        <div class="text-xl font-bold">Suggestions</div>
      </div>

      <!-- Spec Name Row -->
      <div class="grid grid-cols-2 gap-8">
        <FormElement
          label="Spec Name"
          description="A short name for your own reference."
          id="current_spec_name"
          value={current_name}
          disabled={true}
        />
        <div>
          <FormElement
            label="Spec Name"
            description="A short name for your own reference."
            id="suggested_spec_name"
            bind:value={current_name}
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
          >
            <svelte:fragment slot="label_suffix">
              {#if !disabledKeys.has(field.key)}
                {#if !hasAiSuggestion(field.key)}
                  <span
                    class="badge badge-success badge-outline badge-sm gap-1 ml-2"
                  >
                    No changes
                    <svg
                      class="w-3 h-3"
                      viewBox="0 0 24 24"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M16 9L10 15.5L7.5 13M12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C7.02944 3 3 7.02944 3 12C3 16.9706 7.02944 21 12 21Z"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </span>
                {:else}
                  <span
                    class="badge badge-warning badge-outline badge-sm gap-1 ml-2"
                  >
                    Edit suggested
                    <svg
                      class="w-3 h-3"
                      fill="currentColor"
                      viewBox="0 0 256 256"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
                      />
                    </svg>
                  </span>
                {/if}
              {/if}
            </svelte:fragment>
          </FormElement>
        </div>
      {/each}
    </FormContainer>
    <div class="flex flex-row gap-1 mt-2 justify-end">
      <span class="text-xs text-gray-500">or</span>
      <button
        class="link underline text-xs text-gray-500"
        on:click={create_spec}>Create Spec Without Analyzing Changes</button
      >
    </div>
  {/if}
</AppPage>

<Dialog bind:this={analyze_dialog} title="Analyzing Spec">
  <div class="flex flex-col items-center justify-center min-h-[100px]">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
</Dialog>
