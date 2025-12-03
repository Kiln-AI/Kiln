<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import { onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import { createSpec } from "../spec_utils"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_type: SpecType = "behaviour"
  let name = ""

  // Store property values as a Record<string, string | null>
  let property_values: Record<string, string | null> = {}
  let initial_property_values: Record<string, string | null> = {}
  let initialized = false

  // Get field configs for the current spec_type
  $: field_configs = spec_field_configs[spec_type] || []

  onMount(() => {
    const spec_type_param = $page.url.searchParams.get("type")
    if (spec_type_param) {
      spec_type = spec_type_param as SpecType
    }
    name = formatSpecTypeName(spec_type)

    // Initialize property values from field configs
    // Fields with default_value are pre-filled, others start empty
    const fieldConfigs = spec_field_configs[spec_type] || []
    const values: Record<string, string | null> = {}

    for (const field of fieldConfigs) {
      if (field.default_value !== undefined) {
        values[field.key] = field.default_value
      }
    }

    property_values = values
    initial_property_values = { ...values }

    // Override tool_function_name if provided in URL
    const tool_function_name_param =
      $page.url.searchParams.get("tool_function_name")
    if (tool_function_name_param) {
      property_values["tool_function_name"] = tool_function_name_param
      initial_property_values["tool_function_name"] = tool_function_name_param
    }

    initialized = true
  })

  let create_error: KilnError | null = null
  let submitting = false
  let complete = false

  let analyze_dialog: Dialog | null = null
  async function analyze_spec() {
    try {
      create_error = null
      submitting = true

      // Validate required fields
      for (const field of field_configs) {
        if (field.required) {
          const value = property_values[field.key]
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

      // Store form data in sessionStorage to pass to refine page
      const formData = {
        name,
        spec_type,
        property_values,
      }
      sessionStorage.setItem(
        `spec_refine_${project_id}_${task_id}`,
        JSON.stringify(formData),
      )

      // Navigate to review_spec page
      goto(`/specs/${project_id}/${task_id}/review_spec`)
    } catch (error) {
      create_error = createKilnError(error)
      analyze_dialog?.hide()
      submitting = false
    }
  }

  function reset_field(key: string) {
    property_values[key] = initial_property_values[key] ?? null
  }

  function has_form_changes(): boolean {
    if (!initialized) return false
    if (name !== formatSpecTypeName(spec_type)) return true
    for (const key of Object.keys(property_values)) {
      if (property_values[key] !== initial_property_values[key]) return true
    }
    return false
  }

  async function create_spec() {
    try {
      create_error = null
      submitting = true
      complete = false

      // Validate required fields
      for (const field of field_configs) {
        if (field.required) {
          const value = property_values[field.key]
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
        property_values,
      )

      if (spec_id) {
        complete = true
        goto(`/specs/${project_id}/${task_id}/${spec_id}`)
      }
    } catch (error) {
      create_error = createKilnError(error)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Define Spec"
    subtitle={`Template: ${formatSpecTypeName(spec_type)}`}
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
    <FormContainer
      submit_label="Next"
      on:submit={analyze_spec}
      bind:error={create_error}
      bind:submitting
      warn_before_unload={!complete && has_form_changes()}
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
          height={field.height || "base"}
          bind:value={property_values[field.key]}
          optional={!field.required}
          inline_action={initial_property_values[field.key]
            ? {
                handler: () => reset_field(field.key),
                label: "Reset",
              }
            : undefined}
        />
      {/each}
    </FormContainer>
    <div class="flex flex-row gap-1 mt-2 justify-end">
      <span class="text-xs text-gray-500">or</span>
      <button
        class="link underline text-xs text-gray-500"
        on:click={create_spec}>Create Spec Without Analysis</button
      >
    </div>
  </AppPage>
</div>

<Dialog bind:this={analyze_dialog} title="Analyzing Spec">
  <div class="flex flex-col items-center justify-center min-h-[100px]">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
</Dialog>
