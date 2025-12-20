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

  onMount(async () => {
    // Check if kiln-copilot is connected
    try {
      const { data, error } = await client.GET("/api/settings")
      if (!error && data && data["kiln_copilot_api_key"]) {
        has_kiln_copilot = true
      }
    } catch (e) {
      console.error("Failed to check kiln-copilot status", e)
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
  let warn_before_unload = false

  let copilot_upsell_dialog: Dialog | null = null
  let confirm_dont_show_again_dialog: Dialog | null = null
  let has_kiln_copilot = false
  let show_connect_kiln_steps = false
  let connect_steps_component: ConnectKilnCopilotSteps | null = null

  const SKIP_COPILOT_KEY = "skip_kiln_copilot_upsell"

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

      // Check if user has previously skipped the copilot upsell
      const hasSkipped =
        typeof window !== "undefined" &&
        localStorage.getItem(SKIP_COPILOT_KEY) === "true"

      if (hasSkipped) {
        await proceed_to_review()
        return
      }

      // Check if kiln-copilot is connected
      const { data, error } = await client.GET("/api/settings")
      if (error) {
        console.error("Failed to check kiln-copilot status", error)
        await proceed_to_review()
        return
      }

      const has_kiln_copilot = data && data["kiln_copilot_api_key"]

      if (!has_kiln_copilot) {
        submitting = false
        copilot_upsell_dialog?.show()
      } else {
        await proceed_to_review()
      }
    } catch (error) {
      create_error = createKilnError(error)
      submitting = false
    }
  }

  async function proceed_to_review() {
    // Don't warn before unloading since we're intentionally navigating
    warn_before_unload = false

    // Navigate to review_spec page
    await navigateToReviewSpec(
      project_id,
      task_id,
      name,
      spec_type,
      property_values,
      evaluate_full_trace,
    )
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
        evaluate_full_trace,
      )

      complete = true
      goto(`/specs/${project_id}/${task_id}/${spec_id}`)
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
      on:submit={check_kiln_copilot_and_proceed}
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
          on:click={create_spec}>Create Spec Without Analysis</button
        >
      </div>
    {/if}
  </AppPage>
</div>

<Dialog
  bind:this={copilot_upsell_dialog}
  title="Refine Your Spec with Kiln Copilot"
  sub_subtitle="Connect an API key to enable guided spec refinement and evaluation setup"
  on:close={() => {
    show_connect_kiln_steps = false
  }}
  action_buttons={[
    {
      label: "Continue to Refine Spec",
      hide: !show_continue_to_review,
      width: "wide",
      isPrimary: true,
      action: () => {
        proceed_to_review()
        return true
      },
    },
    {
      label: "Skip Refinement & Save",
      hide: show_connect_kiln_steps,
      action: () => {
        create_spec()
        return true
      },
    },
    {
      label: show_connect_kiln_steps ? "Connect" : "Connect API Key",
      hide: show_connect_kiln_steps,
      isPrimary: true,
      asyncAction: async () => {
        if (!show_connect_kiln_steps) {
          show_connect_kiln_steps = true
          return false
        }
        if (connect_steps_component) {
          const success = await connect_steps_component.submitApiKey()
          return success
        }
        return false
      },
    },
  ]}
>
  {#if !show_connect_kiln_steps}
    <div class="flex flex-col gap-4 mt-8">
      <div class="flex flex-row gap-3 items-center">
        <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
        <svg
          class="w-8 h-8 mx-2"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M16 4C18.175 4.01211 19.3529 4.10856 20.1213 4.87694C21 5.75562 21 7.16983 21 9.99826V15.9983C21 18.8267 21 20.2409 20.1213 21.1196C19.2426 21.9983 17.8284 21.9983 15 21.9983H9C6.17157 21.9983 4.75736 21.9983 3.87868 21.1196C3 20.2409 3 18.8267 3 15.9983V9.99826C3 7.16983 3 5.75562 3.87868 4.87694C4.64706 4.10856 5.82497 4.01211 8 4"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M9 13.4L10.7143 15L15 11"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M8 3.5C8 2.67157 8.67157 2 9.5 2H14.5C15.3284 2 16 2.67157 16 3.5V4.5C16 5.32843 15.3284 6 14.5 6H9.5C8.67157 6 8 5.32843 8 4.5V3.5Z"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <div class="flex flex-col gap-1">
          <div class="text-base font-medium text-sm">
            AI-powered spec refinement
          </div>
          <div class="text-gray-500 text-sm">
            Improve clarity and coverage with guided AI suggestions
          </div>
        </div>
      </div>
      <div class="flex flex-row gap-3 items-center">
        <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
        <svg
          class="w-8 h-8 mx-2"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M11.1459 7.02251C11.5259 6.34084 11.7159 6 12 6C12.2841 6 12.4741 6.34084 12.8541 7.02251L12.9524 7.19887C13.0603 7.39258 13.1143 7.48944 13.1985 7.55334C13.2827 7.61725 13.3875 7.64097 13.5972 7.68841L13.7881 7.73161C14.526 7.89857 14.895 7.98205 14.9828 8.26432C15.0706 8.54659 14.819 8.84072 14.316 9.42898L14.1858 9.58117C14.0429 9.74833 13.9714 9.83191 13.9392 9.93531C13.9071 10.0387 13.9179 10.1502 13.9395 10.3733L13.9592 10.5763C14.0352 11.3612 14.0733 11.7536 13.8435 11.9281C13.6136 12.1025 13.2682 11.9435 12.5773 11.6254L12.3986 11.5431C12.2022 11.4527 12.1041 11.4075 12 11.4075C11.8959 11.4075 11.7978 11.4527 11.6014 11.5431L11.4227 11.6254C10.7318 11.9435 10.3864 12.1025 10.1565 11.9281C9.92674 11.7536 9.96476 11.3612 10.0408 10.5763L10.0605 10.3733C10.0821 10.1502 10.0929 10.0387 10.0608 9.93531C10.0286 9.83191 9.95713 9.74833 9.81418 9.58117L9.68403 9.42898C9.18097 8.84072 8.92945 8.54659 9.01723 8.26432C9.10501 7.98205 9.47396 7.89857 10.2119 7.73161L10.4028 7.68841C10.6125 7.64097 10.7173 7.61725 10.8015 7.55334C10.8857 7.48944 10.9397 7.39258 11.0476 7.19887L11.1459 7.02251Z"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M19 9C19 12.866 15.866 16 12 16C8.13401 16 5 12.866 5 9C5 5.13401 8.13401 2 12 2C15.866 2 19 5.13401 19 9Z"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M12 16.0678L8.22855 19.9728C7.68843 20.5321 7.41837 20.8117 7.18967 20.9084C6.66852 21.1289 6.09042 20.9402 5.81628 20.4602C5.69597 20.2495 5.65848 19.8695 5.5835 19.1095C5.54117 18.6804 5.52 18.4658 5.45575 18.2861C5.31191 17.8838 5.00966 17.5708 4.6211 17.4219C4.44754 17.3554 4.24033 17.3335 3.82589 17.2896C3.09187 17.212 2.72486 17.1732 2.52138 17.0486C2.05772 16.7648 1.87548 16.1662 2.08843 15.6266C2.18188 15.3898 2.45194 15.1102 2.99206 14.5509L5.45575 12"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M12 16.0678L15.7715 19.9728C16.3116 20.5321 16.5816 20.8117 16.8103 20.9084C17.3315 21.1289 17.9096 20.9402 18.1837 20.4602C18.304 20.2495 18.3415 19.8695 18.4165 19.1095C18.4588 18.6804 18.48 18.4658 18.5442 18.2861C18.6881 17.8838 18.9903 17.5708 19.3789 17.4219C19.5525 17.3554 19.7597 17.3335 20.1741 17.2896C20.9081 17.212 21.2751 17.1732 21.4786 17.0486C21.9423 16.7648 22.1245 16.1662 21.9116 15.6266C21.8181 15.3898 21.5481 15.1102 21.0079 14.5509L18.5442 12"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <div class="flex flex-col gap-1">
          <div class="text-base font-medium text-sm">
            Automatic eval judge setup
          </div>
          <div class="text-gray-500 text-sm">
            Skip manual configuration with an optimized eval judge
          </div>
        </div>
      </div>
      <div class="flex flex-row gap-3 items-center">
        <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. Attribution: https://www.svgrepo.com/svg/524492/database -->
        <svg
          class="w-8 h-8 mx-2"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M4 18V6"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
          <path
            d="M20 6V18"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
          <path
            d="M12 10C16.4183 10 20 8.20914 20 6C20 3.79086 16.4183 2 12 2C7.58172 2 4 3.79086 4 6C4 8.20914 7.58172 10 12 10Z"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M20 12C20 14.2091 16.4183 16 12 16C7.58172 16 4 14.2091 4 12"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M20 18C20 20.2091 16.4183 22 12 22C7.58172 22 4 20.2091 4 18"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <div class="flex flex-col gap-1">
          <div class="text-base font-medium text-sm">
            Synthetic eval data generation
          </div>
          <div class="text-gray-500 text-sm">
            Instant eval data to measure model performance against your spec
          </div>
        </div>
      </div>
    </div>
  {:else}
    <div class="mb-2">
      <ConnectKilnCopilotSteps
        bind:this={connect_steps_component}
        small={true}
        onSuccess={handle_connect_success}
        showCheckmark={has_kiln_copilot}
      />
    </div>
  {/if}
  <div slot="footer">
    {#if !show_connect_kiln_steps}
      <div class="flex justify-end mt-6">
        <button
          class="link text-xs text-gray-500"
          on:click={() => {
            copilot_upsell_dialog?.close()
            confirm_dont_show_again_dialog?.show()
          }}>Don't show again</button
        >
      </div>
    {/if}
  </div>
</Dialog>

<Dialog
  bind:this={confirm_dont_show_again_dialog}
  title="Don't Show Again?"
  sub_subtitle="You can connect your Kiln Copilot API key later at any time"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
      action: () => {
        return true
      },
    },
    {
      label: "Ok",
      isPrimary: true,
      action: () => {
        if (typeof window !== "undefined") {
          localStorage.setItem(SKIP_COPILOT_KEY, "true")
        }
        return true
      },
    },
  ]}
>
  <div class="flex flex-row gap-1">
    <div class="text-base text-sm">To connect later, go to</div>
    <div class="text-base font-medium text-sm">Settings > Manage Providers</div>
  </div>
</Dialog>
