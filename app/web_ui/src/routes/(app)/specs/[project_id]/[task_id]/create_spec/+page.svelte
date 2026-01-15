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
  import Collapse from "$lib/ui/collapse.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import {
    createSpec,
    navigateToReviewSpec,
    loadSpecFormData,
  } from "../spec_utils"
  import { client } from "$lib/api_client"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_type: SpecType = "desired_behaviour"
  let name = ""

  // Store property values as a Record<string, string | null>
  let property_values: Record<string, string | null> = {}
  let initial_property_values: Record<string, string | null> = {}
  let initialized = false

  // Advanced options
  let evaluate_full_trace = false
  $: is_tool_use_spec = spec_type === "appropriate_tool_use"
  $: is_reference_answer_spec = spec_type === "reference_answer_accuracy"
  $: full_trace_disabled = is_tool_use_spec
  $: show_advanced_options = !is_reference_answer_spec
  $: if (is_tool_use_spec) evaluate_full_trace = true

  // Get field configs for the current spec_type
  $: field_configs = spec_field_configs[spec_type] || []

  let loading = false
  let loading_error: KilnError | null = null

  function spec_type_to_name(spec_type: SpecType): string {
    if (spec_type === "desired_behaviour" || spec_type === "issue") {
      return ""
    }
    return formatSpecTypeName(spec_type)
  }

  onMount(async () => {
    loading = true

    // Check if kiln-copilot is connected
    try {
      const { data, error } = await client.GET("/api/settings")
      if (error) {
        throw error
      }
      if (!data) {
        throw new Error("Failed to load Kiln settings")
      }
      if (data["kiln_copilot_api_key"]) {
        has_kiln_copilot = true
      } else {
        has_kiln_copilot = false
      }
    } catch (e) {
      loading_error = createKilnError(e)
    }

    // Check for URL params first (fresh navigation from select_template)
    const spec_type_param = $page.url.searchParams.get("type")
    const has_url_params = spec_type_param !== null

    // Check if we have saved form data from a back navigation
    const formData = loadSpecFormData(project_id, task_id)

    if (formData && !has_url_params) {
      // Restore form state
      spec_type = formData.spec_type
      name = formData.name
      property_values = { ...formData.property_values }
      initial_property_values = { ...formData.property_values }
      evaluate_full_trace = formData.evaluate_full_trace
      initialized = true
      loading = false
      return
    }

    // If no stored data and no URL params, redirect to specs list
    // This happens when user navigates back after creating a spec
    if (!formData && !has_url_params) {
      goto(`/specs/${project_id}/${task_id}`)
      return
    }

    // Normal initialization with URL params
    if (spec_type_param) {
      spec_type = spec_type_param as SpecType
    }
    name = spec_type_to_name(spec_type)

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
    loading = false
  })

  let next_error: KilnError | null = null

  let submitting = false
  let complete = false
  let warn_before_unload = false

  let has_kiln_copilot = false

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

  async function check_kiln_copilot_and_proceed() {
    try {
      next_error = null
      submitting = true

      validateRequiredFields()

      if (has_kiln_copilot) {
        await proceed_to_review()
      } else {
        do_create_spec((e) => (next_error = e))
      }
    } catch (error) {
      next_error = createKilnError(error)
      submitting = false
    }
  }

  async function proceed_to_review() {
    // Don't warn before unloading since we're intentionally navigating
    warn_before_unload = false

    try {
      // Navigate to review_spec page
      await navigateToReviewSpec(
        project_id,
        task_id,
        name,
        spec_type,
        property_values,
        evaluate_full_trace,
      )
    } catch (error) {
      warn_before_unload = true
      next_error = createKilnError(error)
    }
  }

  function reset_field(key: string) {
    property_values[key] = initial_property_values[key] ?? null
  }

  function has_form_changes(): boolean {
    if (!initialized) return false
    if (name !== spec_type_to_name(spec_type)) return true
    for (const key of Object.keys(property_values)) {
      if (property_values[key] !== initial_property_values[key]) return true
    }
    return false
  }

  function validateRequiredFields() {
    for (const field of field_configs) {
      if (field.required) {
        const value = property_values[field.key]
        if (!value || !value.trim()) {
          throw new Error(`${field.label} is required`)
        }
      }
    }
  }

  async function do_create_spec(set_error: (error: KilnError | null) => void) {
    try {
      set_error(null)
      submitting = true
      complete = false

      validateRequiredFields()

      const use_kiln_copilot = false
      const spec_id = await createSpec(
        project_id,
        task_id,
        name,
        spec_type,
        property_values,
        use_kiln_copilot,
        evaluate_full_trace,
      )

      complete = true
      warn_before_unload = false
      // Replace history so browser back goes to templates
      goto(`/specs/${project_id}/${task_id}/${spec_id}`, { replaceState: true })
    } catch (error) {
      set_error(createKilnError(error))
    } finally {
      submitting = false
    }
  }

  // For main form - errors show in FormContainer
  function create_spec_from_form() {
    do_create_spec((e) => (next_error = e))
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create Spec"
    subtitle="A specification describes a behaviour to enforce or avoid for your task. Adding specs lets us measure and optimze quality."
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
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div class="text-error text-sm">
        {loading_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <FormContainer
        submit_label={has_kiln_copilot ? "Analyze with Copilot" : "Create Spec"}
        on:submit={check_kiln_copilot_and_proceed}
        bind:error={next_error}
        bind:submitting
        compact_button={true}
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
      {#if has_kiln_copilot}
        <div class="flex flex-row gap-1 mt-4 justify-end">
          <span class="text-sm text-gray-500">or</span>
          <button
            class="link underline text-sm text-gray-500"
            on:click={create_spec_from_form}>Create without Copilot</button
          >
        </div>
      {/if}
    {/if}
  </AppPage>
</div>
