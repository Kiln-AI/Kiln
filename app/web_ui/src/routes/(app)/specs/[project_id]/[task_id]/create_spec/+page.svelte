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
  import Dialog from "$lib/ui/dialog.svelte"
  import { client } from "$lib/api_client"
  import ConnectKilnCopilotSteps from "$lib/ui/kiln_copilot/connect_kiln_copilot_steps.svelte"

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
  let create_error: KilnError | null = null

  let submitting = false
  let complete = false
  let warn_before_unload = false

  let copilot_v_manual_dialog: Dialog | null = null
  let has_kiln_copilot = false
  let show_connect_kiln_steps = false

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

      if (!has_kiln_copilot) {
        submitting = false
        copilot_v_manual_dialog?.show()
      } else {
        await proceed_to_review()
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

  let show_continue_to_review = false
  async function handle_connect_success() {
    has_kiln_copilot = true
    show_continue_to_review = true
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

      const spec_id = await createSpec(
        project_id,
        task_id,
        name,
        spec_type,
        property_values,
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

  // For dialog - errors show in the card
  function create_spec_from_dialog() {
    do_create_spec((e) => (create_error = e))
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
    sub_subtitle={`Template: ${formatSpecTypeName(spec_type)}`}
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
        submit_label={has_kiln_copilot ? "Refine Spec with Copilot" : "Next"}
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
              description="When enabled, this spec will be judged on the full conversation history including intermediate steps and tool calls. When disabled, only the final answer is evaluated."
              info_description={full_trace_disabled
                ? "Tool use specs always evaluate the full conversation history to analyze tool calls."
                : "Enable this for specs that need to evaluate reasoning steps, tool usage, or intermediate outputs."}
            />
          </Collapse>
        {/if}
      </FormContainer>
      {#if has_kiln_copilot}
        <div class="flex flex-row gap-1 mt-2 justify-end">
          <span class="text-xs text-gray-500">or</span>
          <button
            class="link underline text-xs text-gray-500"
            on:click={create_spec_from_form}>Create Spec Without Copilot</button
          >
        </div>
      {/if}
    {/if}
  </AppPage>
</div>

<Dialog
  bind:this={copilot_v_manual_dialog}
  title={show_connect_kiln_steps
    ? "Connect Kiln Copilot"
    : "Choose your workflow"}
  sub_subtitle={show_connect_kiln_steps
    ? "Follow the steps below to setup Kiln Copilot"
    : "Select a workflow for defining and evaluating this spec"}
  width={show_connect_kiln_steps ? "normal" : "wide"}
  on:close={() => {
    show_connect_kiln_steps = false
    create_error = null
  }}
>
  {#if show_connect_kiln_steps}
    <div class="flex flex-col">
      <ConnectKilnCopilotSteps
        showTitle={false}
        onSuccess={handle_connect_success}
        showCheckmark={has_kiln_copilot}
      />
      {#if show_continue_to_review}
        <button
          class="btn btn-primary mt-4 w-full"
          on:click={async () => {
            await proceed_to_review()
            copilot_v_manual_dialog?.close()
          }}
        >
          Continue to Refine Spec
        </button>
      {/if}
      <button
        class="link text-center text-sm mt-8"
        on:click={() => {
          show_connect_kiln_steps = false
        }}
      >
        Cancel setting up Kiln Copilot
      </button>
    </div>
  {:else}
    <div class="mt-4 max-w-[500px] mx-auto">
      <div class="overflow-x-auto rounded-lg border">
        <table class="table table-fixed w-full">
          <colgroup>
            <col class="w-[160px]" />
            <col class="w-[140px]" />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th></th>
              <th class="text-center">Manual</th>
              <th class="text-center">
                <div class="flex items-center justify-center gap-2">
                  <img
                    src="/images/animated_logo.svg"
                    alt="Kiln Copilot"
                    class="size-4"
                  />
                  <span>Kiln Copilot</span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th class="font-bold text-xs text-gray-500">Eval judge setup</th>
              <td class="text-center">Manual</td>
              <td class="text-center text-primary">Automatic</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-gray-500"
                >Edge case discovery</th
              >
              <td class="text-center">Manual</td>
              <td class="text-center text-primary">Automatic</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-gray-500">Eval data creation</th
              >
              <td class="text-center">Manual</td>
              <td class="text-center text-primary">Automatic</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-base-content/60"
                >Eval accuracy</th
              >
              <td class="text-center">Varies</td>
              <td class="text-center text-primary">High</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-gray-500">Approx. effort</th>
              <td class="text-center">~20 min</td>
              <td class="text-center text-primary">~3 min</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-base-content/60"
                >Kiln account</th
              >
              <td class="text-center">Optional</td>
              <td class="text-center text-primary">Required</td>
            </tr>
          </tbody>
        </table>
      </div>
      <table class="table-fixed w-full mt-4">
        <colgroup>
          <col class="w-[160px]" />
          <col class="w-[140px]" />
          <col />
        </colgroup>
        <tbody>
          <tr>
            <td></td>
            <td class="text-center">
              <button
                class="btn btn-outline btn-sm"
                on:click={create_spec_from_dialog}
              >
                Create Manually
              </button>
            </td>
            <td class="text-center">
              <button
                class="btn btn-primary btn-sm"
                on:click={() => {
                  show_connect_kiln_steps = true
                }}
              >
                Connect Kiln Copilot
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      {#if create_error}
        <div class="alert alert-error mt-4">
          <span>{create_error.message}</span>
        </div>
      {/if}
    </div>
  {/if}
</Dialog>
