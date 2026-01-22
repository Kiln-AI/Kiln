<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, onDestroy } from "svelte"
  import { autofillSpecName } from "$lib/utils/formatters"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType, ModelProviderName, Task } from "$lib/types"
  import { goto } from "$app/navigation"
  import { spec_field_configs } from "../select_template/spec_templates"
  import {
    checkKilnCopilotAvailable,
    checkDefaultRunConfigHasTools,
    buildSpecDefinition,
    type SuggestedEdit,
  } from "../spec_utils"
  import {
    createSpec,
    type JudgeInfo,
    type ReviewedExample,
  } from "./spec_persistence"
  import { client } from "$lib/api_client"
  import {
    load_task,
    available_models,
    load_available_models,
  } from "$lib/stores"
  import CreateSpecForm from "./create_spec_form.svelte"
  import ReviewExamples from "./review_examples.svelte"
  import RefineSpec from "./refine_spec.svelte"
  import SpecAnalyzingAnimation from "../spec_analyzing_animation.svelte"
  import type { FewShotExample } from "$lib/utils/few_shot_example"
  import { build_prompt_with_few_shot } from "$lib/utils/few_shot_example"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  // State machine for the spec builder flow
  //  create - Initial form for spec creation
  //  analyzing_for_review - Loading state while calling clarify_spec API
  //  review - Review examples table with pass/fail buttons
  //  refining - Loading state while calling refine_spec API
  //  refine - Review AI-suggested refinements side-by-side
  type BuilderState =
    | "create"
    | "analyzing_for_review"
    | "review"
    | "refining"
    | "refine"

  let current_state: BuilderState = "create"

  // Form state (shared across all states)
  let spec_type: SpecType = "desired_behaviour"
  let name = ""
  let property_values: Record<string, string | null> = {}
  let initial_property_values: Record<string, string | null> = {}
  let evaluate_full_trace = false

  // Copilot availability
  let has_kiln_copilot = false
  let default_run_config_has_tools = false

  // Task data (loaded once in initialize)
  let task: Task | null = null
  $: task_input_schema = task?.input_json_schema
    ? JSON.stringify(task.input_json_schema)
    : ""
  $: task_output_schema = task?.output_json_schema
    ? JSON.stringify(task.output_json_schema)
    : ""

  // Few-shot example for improving API calls
  let few_shot_example: FewShotExample | null = null
  let task_prompt_with_few_shot: string = ""

  // Update the prompt when few_shot_example or task changes
  async function update_task_prompt_with_few_shot() {
    if (!task) {
      task_prompt_with_few_shot = ""
      return
    }
    try {
      const examples = few_shot_example ? [few_shot_example] : []
      task_prompt_with_few_shot = await build_prompt_with_few_shot(
        project_id,
        task_id,
        examples,
      )
    } catch (e) {
      console.error("Failed to build prompt with few-shot:", e)
      // Fallback to just the instruction
      task_prompt_with_few_shot = task?.instruction || ""
    }
  }

  // Reactively update when example changes
  $: void (few_shot_example && update_task_prompt_with_few_shot())

  // Review state
  type ReviewRow = ReviewedExample & { id: string }

  let review_rows: ReviewRow[] = []
  let reviewed_examples: ReviewedExample[] = []

  let judge_info: JudgeInfo | null = null

  // Refine state
  let refined_property_values: Record<string, string | null> = {}
  // Keys are field keys
  let suggested_edits: Record<string, SuggestedEdit> = {}
  let out_of_scope_feedback: string = ""

  // Loading/error state
  let loading = true
  let loading_error: KilnError | null = null
  let error: KilnError | null = null

  // Submission state
  let submitting = false
  let saving_spec = false // Full-page loading when saving spec directly (via secondary buttons)
  let complete = false

  // AbortController for cancelling in-flight Copilot API requests
  let copilot_abort_controller: AbortController | null = null

  function abort_copilot_request() {
    copilot_abort_controller?.abort()
    copilot_abort_controller = null
  }

  function new_copilot_abort_signal(): AbortSignal {
    abort_copilot_request()
    copilot_abort_controller = new AbortController()
    return copilot_abort_controller.signal
  }

  function is_abort_error(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError"
  }

  onDestroy(() => {
    abort_copilot_request()
  })

  // Get field configs for the current spec_type
  $: field_configs = spec_field_configs[spec_type] || []

  // Get the available providers for copilot
  $: providers = $available_models.map(
    (m) => m.provider_id as ModelProviderName,
  )

  // Advanced options
  $: is_tool_use_spec = spec_type === "appropriate_tool_use"
  $: is_reference_answer_spec = spec_type === "reference_answer_accuracy"
  $: full_trace_disabled = is_tool_use_spec
  $: hide_include_conversation_history = is_reference_answer_spec
  $: if (is_tool_use_spec) evaluate_full_trace = true

  // Tool call and RAG specs don't support copilot
  // Also disable copilot when the default run config has tools (tool calling not supported yet)
  $: copilot_enabled =
    has_kiln_copilot &&
    !is_tool_use_spec &&
    !is_reference_answer_spec &&
    !default_run_config_has_tools

  // Initialize form from URL params
  async function initialize() {
    loading = true
    loading_error = null

    try {
      // Check if kiln-copilot is connected
      has_kiln_copilot = await checkKilnCopilotAvailable()

      // Load available models for later API calls
      await load_available_models()

      // Load the task (used by copilot API calls)
      task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Failed to load task")
      }

      // Check if default run config has tools (copilot doesn't support tool calling)
      default_run_config_has_tools = await checkDefaultRunConfigHasTools(
        project_id,
        task,
      )

      // Get spec type from URL params
      const spec_type_param = $page.url.searchParams.get("type")
      if (!spec_type_param) {
        console.error("No spec type provided")
        complete = true
        goto(`/specs/${project_id}/${task_id}`)
        return
      }

      spec_type = spec_type_param as SpecType
      name = autofillSpecName(spec_type)

      // Initialize property values from field configs
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
    } catch (e) {
      loading_error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  onMount(() => {
    initialize()
  })

  // Shared logic for analyzing spec with clarify_spec API
  // If values_to_use is provided, property_values will be updated to match on success
  async function analyzeSpecForReview(
    values_to_use: Record<string, string | null> = property_values,
  ) {
    if (!task) {
      throw new Error("Task not loaded")
    }

    current_state = "analyzing_for_review"

    const spec_rendered_prompt_template = buildSpecDefinition(
      spec_type,
      values_to_use,
    )

    const { data, error: api_error } = await client.POST(
      "/api/copilot/clarify_spec",
      {
        body: {
          task_prompt_with_few_shot,
          task_input_schema,
          task_output_schema,
          spec_rendered_prompt_template,
          num_samples_per_topic: 10,
          num_topics: 5,
          providers: providers,
          num_exemplars: 5, // TODO: 10 topics, 10 samples per topic, 10 exemplars
        },
        signal: new_copilot_abort_signal(),
      },
    )

    if (api_error) {
      throw api_error
    }

    if (!data) {
      throw new Error("Failed to analyze spec for review. Please try again.")
    }

    judge_info = {
      prompt: data.judge_prompt,
      model_name: data.model_id,
      model_provider: data.model_provider,
    }

    review_rows = data.examples_for_feedback.map((example, index) => ({
      id: String(index + 1),
      input: example.input,
      output: example.output,
      model_says_meets_spec: !example.exhibits_issue,
      user_says_meets_spec: undefined,
      feedback: "",
    }))

    // Update property_values on success (important for refined spec flow)
    property_values = { ...values_to_use }

    current_state = "review"
  }

  // Handler for "Analyze with Copilot" button
  async function handle_analyze_with_copilot() {
    error = null
    try {
      await analyzeSpecForReview()
    } catch (e) {
      if (is_abort_error(e)) return
      console.error("Kiln Copilot failed to analyze spec:", e)
      error = new KilnError("Kiln Copilot failed to analyze. Please try again.")
      current_state = "create"
    } finally {
      submitting = false
    }
  }

  // Collect reviewed examples from current review rows
  function currentReviewedExamples(): ReviewedExample[] {
    return review_rows
      .filter((row) => row.user_says_meets_spec !== undefined)
      .map((row) => ({
        input: row.input,
        output: row.output,
        user_says_meets_spec: row.user_says_meets_spec ?? false,
        feedback: row.feedback,
        model_says_meets_spec: row.model_says_meets_spec,
      }))
  }

  // Shared logic for creating and saving a spec
  async function saveSpec(
    values: Record<string, string | null>,
    use_kiln_copilot: boolean,
    examples: ReviewedExample[],
    signal?: AbortSignal,
  ) {
    const spec_id = await createSpec(
      project_id,
      task_id,
      task?.instruction || "",
      task_prompt_with_few_shot,
      name,
      spec_type,
      values,
      use_kiln_copilot,
      evaluate_full_trace,
      examples,
      judge_info,
      signal,
    )

    complete = true
    goto(`/specs/${project_id}/${task_id}/${spec_id}`)
  }

  // Handler for creating spec without copilot
  async function handle_create_spec_without_copilot() {
    error = null
    try {
      saving_spec = true
      await saveSpec(property_values, false, [])
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
      saving_spec = false
    }
  }

  // Handler for creating spec from review (all feedback aligned)
  async function handle_create_spec_from_review(skip_review = false) {
    error = null
    try {
      // Use full-page spinner for skip_review (secondary button), form spinner otherwise
      if (skip_review) {
        saving_spec = true
      }

      await saveSpec(
        property_values,
        true,
        reviewed_examples,
        new_copilot_abort_signal(),
      )
    } catch (e) {
      if (is_abort_error(e)) return
      console.error("Kiln Copilot failed to create spec:", e)
      error = new KilnError(
        "Kiln Copilot failed to create spec. Please try again.",
      )
    } finally {
      submitting = false
      saving_spec = false
    }
  }

  // Handler for continuing to refine (feedback misaligned)
  async function handle_continue_to_refine() {
    try {
      error = null
      current_state = "refining"

      if (!task) {
        throw new Error("Task not loaded")
      }

      // Store current reviewed examples
      const currentExamples = currentReviewedExamples()
      reviewed_examples = [...reviewed_examples, ...currentExamples]

      // Build spec info
      const spec_fields: Record<string, string> = {}
      const spec_field_current_values: Record<string, string> = {}

      for (const field of field_configs) {
        spec_fields[field.key] = field.description
        spec_field_current_values[field.key] = property_values[field.key] || ""
      }

      // Convert reviewed examples to API format
      const examples_with_feedback = currentExamples.map((example) => ({
        user_rating_exhibits_issue_correct:
          example.model_says_meets_spec === example.user_says_meets_spec,
        user_feedback: example.feedback,
        input: example.input,
        output: example.output,
        exhibits_issue: !example.user_says_meets_spec,
      }))

      if (examples_with_feedback.length === 0) {
        throw new Error(
          "No valid reviewed examples with feedback to refine spec",
        )
      }

      const { data, error: api_error } = await client.POST(
        "/api/copilot/refine_spec",
        {
          body: {
            task_prompt_with_few_shot,
            task_input_schema: task.input_json_schema
              ? JSON.stringify(task.input_json_schema)
              : "",
            task_output_schema: task.output_json_schema
              ? JSON.stringify(task.output_json_schema)
              : "",
            task_info: {
              task_prompt: task.instruction || "",
              few_shot_examples: "",
            },
            spec: {
              spec_fields,
              spec_field_current_values,
            },
            examples_with_feedback,
          },
          signal: new_copilot_abort_signal(),
        },
      )

      if (api_error) {
        throw api_error
      }

      // Build refined_property_values and suggested_edits
      refined_property_values = { ...property_values }
      suggested_edits = {}
      out_of_scope_feedback = data.out_of_scope_feedback || ""
      if (data.new_proposed_spec_edits) {
        for (const [field_key, edit] of Object.entries(
          data.new_proposed_spec_edits,
        )) {
          refined_property_values[field_key] = edit.proposed_edit
          suggested_edits[field_key] = {
            proposed_value: edit.proposed_edit,
            reason_for_edit: edit.reason_for_edit || "",
          }
        }
      }

      current_state = "refine"
    } catch (e) {
      if (is_abort_error(e)) return
      console.error("Kiln Copilot failed to refine spec:", e)
      error = new KilnError("Kiln Copilot failed to refine. Please try again.")
      current_state = "review"
    } finally {
      submitting = false
    }
  }

  // Handler for analyzing refined spec (go back to review with updated values)
  async function handle_analyze_refined_spec() {
    error = null
    try {
      // Pass suggested values - property_values will be updated on success
      await analyzeSpecForReview(refined_property_values)
    } catch (e) {
      if (is_abort_error(e)) return
      console.error("Kiln Copilot failed to analyze refined spec:", e)
      error = new KilnError("Kiln Copilot failed to analyze. Please try again.")
      current_state = "refine"
    } finally {
      submitting = false
    }
  }

  // Handler for creating spec from refine (skip further review)
  async function handle_create_spec_from_refine(secondary_button = false) {
    error = null
    try {
      // Use full-page spinner for secondary button, form spinner otherwise
      if (secondary_button) {
        saving_spec = true
      }
      await saveSpec(
        refined_property_values,
        true,
        reviewed_examples,
        new_copilot_abort_signal(),
      )
    } catch (e) {
      if (is_abort_error(e)) return
      console.error("Kiln Copilot failed to create spec:", e)
      error = new KilnError(
        "Kiln Copilot failed to create spec. Please try again.",
      )
    } finally {
      submitting = false
      saving_spec = false
    }
  }

  // Page layout helpers based on current state
  function getPageTitle(state: BuilderState): string {
    switch (state) {
      case "create":
        return "Create Spec"
      case "analyzing_for_review":
      case "review":
        return "Copilot: Review and Refine"
      case "refining":
      case "refine":
        return "Copilot: Review Suggested Refinements"
    }
  }

  function getPageSubtitle(state: BuilderState): string | undefined {
    switch (state) {
      case "create":
        return "A specification describes a behaviour to enforce or avoid for your task. Adding specs lets us measure and optimize quality."
      case "analyzing_for_review":
      case "refining":
        return undefined
      case "review":
        return "Improve your spec and judge with AI guidance."
      case "refine":
        return "Polish your spec to be analyzed further."
    }
  }

  $: num_suggested_edits = Object.keys(suggested_edits).length

  function getPageClass(state: BuilderState): string {
    if (state === "review") return "max-w-[1400px]"
    if (state === "refine" && num_suggested_edits > 0) return "max-w-[1400px]"
    if (state === "analyzing_for_review" || state === "refining") return ""
    return "max-w-[900px]"
  }

  $: page_title = getPageTitle(current_state)
  $: page_subtitle = getPageSubtitle(current_state)
  $: page_class = getPageClass(current_state)

  // Warn before unload when there are unsaved changes
  $: warn_before_unload = !complete && !loading
</script>

<div class={page_class}>
  <AppPage
    title={page_title}
    subtitle={page_subtitle}
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
    {#if loading || saving_spec}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div class="text-error text-sm">
        {loading_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else if current_state === "create"}
      <CreateSpecForm
        bind:name
        bind:property_values
        {initial_property_values}
        bind:evaluate_full_trace
        {field_configs}
        {copilot_enabled}
        {hide_include_conversation_history}
        {full_trace_disabled}
        bind:error
        bind:submitting
        {warn_before_unload}
        {project_id}
        {task_id}
        bind:few_shot_example
        on:analyze_with_copilot={handle_analyze_with_copilot}
        on:create_without_copilot={handle_create_spec_without_copilot}
      />
    {:else if current_state === "analyzing_for_review"}
      <SpecAnalyzingAnimation />
    {:else if current_state === "refining"}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if current_state === "review"}
      <ReviewExamples
        {name}
        {spec_type}
        {property_values}
        bind:review_rows
        bind:error
        bind:submitting
        {warn_before_unload}
        on:create_spec={() => handle_create_spec_from_review(false)}
        on:continue_to_refine={handle_continue_to_refine}
        on:create_spec_secondary={() => handle_create_spec_from_review(true)}
      />
    {:else if current_state === "refine"}
      <RefineSpec
        bind:name
        original_property_values={property_values}
        bind:refined_property_values
        {suggested_edits}
        {out_of_scope_feedback}
        {field_configs}
        bind:error
        bind:submitting
        {warn_before_unload}
        on:analyze_refined={handle_analyze_refined_spec}
        on:create_spec={() => handle_create_spec_from_refine(false)}
        on:create_spec_secondary={() => handle_create_spec_from_refine(true)}
      />
    {/if}
  </AppPage>
</div>
