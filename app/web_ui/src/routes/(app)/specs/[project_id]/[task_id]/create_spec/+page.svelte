<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { autofillSpecName, formatSpecTypeName } from "$lib/utils/formatters"
  import { onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import FormElement from "$lib/utils/form_element.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import { createSpec, navigateToReviewSpec } from "../spec_utils"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_type: SpecType = "desired_behaviour"
  let name = ""

  // Store property values as a Record<string, string | null>
  let property_values: Record<string, string | null> = {}
  let initial_property_values: Record<string, string | null> = {}
  let initialized = false

  // Get field configs for the current spec_type
  $: field_configs = spec_field_configs[spec_type] || []

  onMount(() => {
    // Check for URL params first (fresh navigation from select_template)
    const spec_type_param = $page.url.searchParams.get("type")
    const has_url_params = spec_type_param !== null

    // Check if we have saved form data from a back navigation
    const formDataKey = `spec_refine_${project_id}_${task_id}`
    const storedData = sessionStorage.getItem(formDataKey)

    if (storedData && !has_url_params) {
      try {
        const formData = JSON.parse(storedData)
        // Restore form state
        spec_type = formData.spec_type || "desired_behaviour"
        name = formData.name || ""
        property_values = { ...formData.property_values }
        initial_property_values = { ...formData.property_values }
        initialized = true
        return
      } catch (error) {
        // If parsing fails, continue with normal initialization
        console.error("Failed to restore form data:", error)
      }
    }

    // If no stored data and no URL params, redirect to specs list
    // This happens when user navigates back after creating a spec
    if (!storedData && !has_url_params) {
      goto(`/specs/${project_id}/${task_id}`)
      return
    }

    // Normal initialization with URL params
    if (spec_type_param) {
      spec_type = spec_type_param as SpecType
    }
    name = autofillSpecName(spec_type)

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
  let warn_before_unload = false
  let skip_analysis = false
  let form_container: FormContainer | null = null

  $: void (name, property_values, initialized, update_warn_before_unload())

  function update_warn_before_unload() {
    if (!initialized) {
      warn_before_unload = false
      return
    }
    if (complete) {
      warn_before_unload = false
      return
    }
    warn_before_unload = has_form_changes()
  }

  async function handle_submit() {
    try {
      create_error = null
      submitting = true

      warn_before_unload = false

      if (skip_analysis) {
        await create_spec()
      } else {
        await navigateToReviewSpec(
          project_id,
          task_id,
          name,
          spec_type,
          property_values,
        )
      }
    } catch (error) {
      create_error = createKilnError(error)
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
    const spec_id = await createSpec(
      project_id,
      task_id,
      name,
      spec_type,
      property_values,
    )

    if (spec_id) {
      complete = true
      warn_before_unload = false
      goto(`/specs/${project_id}/${task_id}/${spec_id}`)
    }
  }

  async function handle_skip_analysis() {
    skip_analysis = true
    await form_container?.validate_and_submit()
    skip_analysis = false
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
      bind:this={form_container}
      submit_label="Next"
      on:submit={handle_submit}
      bind:error={create_error}
      bind:submitting
      {warn_before_unload}
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
        on:click={handle_skip_analysis}>Create Spec Without Analysis</button
      >
    </div>
  </AppPage>
</div>
