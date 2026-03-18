<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, onDestroy, tick } from "svelte"
  import { autofillSpecName } from "$lib/utils/formatters"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type {
    SpecType,
    ModelProviderName,
    Task,
    QuestionSet,
    SubmitAnswersRequest,
    QuestionWithAnswer,
    SpecProperties,
    SyntheticDataGenerationStepConfigApi,
    SyntheticDataGenerationSessionConfigApi,
    ReviewedExample,
  } from "$lib/types"
  import { goto } from "$app/navigation"
  import { spec_field_configs } from "../select_template/spec_templates"
  import {
    checkDefaultRunConfigHasTools,
    buildSpecDefinition,
    type SuggestedEdit,
    type ReviewRow,
  } from "../spec_utils"
  import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"
  import { client } from "$lib/api_client"
  import {
    load_task,
    available_models,
    load_available_models,
  } from "$lib/stores"
  import CreateSpecForm from "./create_spec_form.svelte"
  import ReviewExamples from "./review_examples.svelte"
  import RefineSpec from "./refine_spec.svelte"
  import SpecAnalyzingAnimation from "./animations/spec_analyzing_animation.svelte"
  import QuestioningAnimation from "./animations/questioning_animation.svelte"
  import RefiningAnimation from "./animations/refining_animation.svelte"
  import type { FewShotExample } from "$lib/utils/few_shot_example"
  import { build_prompt_with_few_shot } from "$lib/utils/few_shot_example"
  import Questions from "./questions.svelte"
  import posthog from "posthog-js"
  import SavingAnimation from "./animations/saving_animation.svelte"

  const CLARIFY_SPEC_NUM_SAMPLES_PER_TOPIC = 10
  const CLARIFY_SPEC_NUM_TOPICS = 10
  const CLARIFY_SPEC_NUM_EXEMPLARS = 10

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  // State machine for the spec builder flow
  //  create - Initial form for spec creation
  //  questioning - Loading state while calling question_spec API
  //  questions - Showing the questions to the user
  //  analyzing_for_review - Loading state while calling clarify_spec API
  //  review - Review examples table with pass/fail buttons
  //  refining - Loading state while calling refine_spec API
  //  refine - Review AI-suggested refinements side-by-side
  type BuilderState =
    | "create"
    | "questioning"
    | "questions"
    | "analyzing_for_review"
    | "review"
    | "refining"
    | "refine"
    | "saving_with_copilot"

  let current_state: BuilderState = "create"
  let has_questioned_spec = false

  // Form state (shared across all states)
  let spec_type: SpecType = "desired_behaviour"
  let name = ""
  let property_values: Record<string, string | null> = {}
  let initial_property_values: Record<string, string | null> = {}
  let evaluate_full_trace = false

  // Tool use spec: tool_id is not a form field but is required in the saved properties
  let selected_tool_id: string | null = null

  // Copilot availability
  let has_kiln_copilot = false
  let default_run_config_has_tools = false

  // Task data (loaded once in initialize)
  let task: Task | null = null
  $: task_input_schema = task?.input_json_schema ?? ""
  $: task_output_schema = task?.output_json_schema ?? ""

  // Few-shot example for improving API calls
  let few_shot_example: FewShotExample | null = null
  let has_unsaved_manual_entry: boolean = false
  let task_prompt_with_example: string = ""
  let is_prompt_building: boolean = false

  // Update the prompt when few_shot_example or task changes
  async function update_task_prompt_with_example() {
    if (!task) {
      task_prompt_with_example = ""
      return
    }
    is_prompt_building = true
    try {
      const examples = few_shot_example ? [few_shot_example] : []
      task_prompt_with_example = await build_prompt_with_few_shot(
        project_id,
        task_id,
        examples,
      )
    } catch {
      // Fallback to just the instruction
      task_prompt_with_example = task?.instruction || ""
    } finally {
      is_prompt_building = false
    }
  }

  // Reactively update when example or task changes
  $: void (few_shot_example, task, update_task_prompt_with_example())

  // Question state
  let question_set: QuestionSet | null = null

  // Review state
  let review_rows: ReviewRow[] = []
  let reviewed_examples: ReviewedExample[] = []

  let judge_info: SyntheticDataGenerationStepConfigApi | null = null
  let sdg_session_config: SyntheticDataGenerationSessionConfigApi | null = null

  // Refine state
  let refined_property_values: Record<string, string | null> = {}
  // Keys are field keys
  let suggested_edits: Record<string, SuggestedEdit> = {}
  let not_incorporated_feedback: string = ""

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
  $: hide_full_trace_option = is_reference_answer_spec
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
        throw new KilnError("Failed to load task.")
      }

      // Check if default run config has tools (copilot doesn't support tool calling)
      default_run_config_has_tools = await checkDefaultRunConfigHasTools(
        project_id,
        task,
      )

      // Get spec type from URL params
      const spec_type_param = $page.url.searchParams.get("type")
      if (!spec_type_param) {
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

      // Override tool fields if provided in URL
      const tool_function_name_param =
        $page.url.searchParams.get("tool_function_name")
      if (tool_function_name_param) {
        property_values["tool_function_name"] = tool_function_name_param
        initial_property_values["tool_function_name"] = tool_function_name_param
      }
      selected_tool_id = $page.url.searchParams.get("tool_id")
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
      throw new KilnError("Task not loaded.")
    }

    current_state = "analyzing_for_review"

    const target_specification = buildSpecDefinition(spec_type, values_to_use)

    const { data, error: api_error } = await client.POST(
      "/api/copilot/clarify_spec",
      {
        body: {
          target_task_info: {
            task_prompt: task_prompt_with_example,
            task_input_schema,
            task_output_schema,
          },
          target_specification,
          num_samples_per_topic: CLARIFY_SPEC_NUM_SAMPLES_PER_TOPIC,
          num_topics: CLARIFY_SPEC_NUM_TOPICS,
          providers: providers,
          num_exemplars: CLARIFY_SPEC_NUM_EXEMPLARS,
        },
        signal: new_copilot_abort_signal(),
      },
    )

    if (api_error) {
      throw api_error
    }

    if (!data) {
      throw new KilnError(
        "Failed to analyze spec for review. Please try again.",
      )
    }

    // Save generation results
    judge_info = data.judge_result
    sdg_session_config = data.sdg_session_config

    review_rows = data.examples_for_feedback.map((example, index) => ({
      row_id: String(index + 1),
      input: example.input,
      output: example.output,
      model_says_meets_spec: !example.fails_specification,
      user_says_meets_spec: undefined,
      feedback: "",
    }))

    posthog.capture("copilot_clarify_spec", {
      spec_type: spec_type,
    })

    // Update property_values on success (important for refined spec flow)
    property_values = { ...values_to_use }

    current_state = "review"
  }

  // Handler for "Analyze with Copilot" button
  async function handle_analyze_with_copilot() {
    error = null

    try {
      // Check for unsaved manual entry
      if (has_unsaved_manual_entry) {
        error = new KilnError("Please save your task sample before analyzing.")
        await tick() // Yield to let Svelte process FormContainer's submitting=true before finally sets it false
        return
      }

      if (!has_questioned_spec) {
        await get_question_set()
      } else {
        await analyzeSpecForReview()
      }
    } catch (e) {
      if (is_abort_error(e)) return
      has_questioned_spec = false
      error = createKilnError(e)
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
    reviewed_examples: ReviewedExample[],
    signal?: AbortSignal,
  ) {
    // Build definition and properties on the client side
    const definition = buildSpecDefinition(spec_type, values)

    // Build properties object with spec_type, filtering out null and empty values
    const filteredValues = Object.fromEntries(
      Object.entries(values).filter(
        ([_, value]) => value !== null && value.trim() !== "",
      ),
    )
    const properties = {
      spec_type: spec_type,
      ...filteredValues,
      ...(selected_tool_id ? { tool_id: selected_tool_id } : {}),
    } as SpecProperties

    // Call the appropriate endpoint based on whether copilot is being used
    let spec_id: string | null | undefined
    if (use_kiln_copilot) {
      if (!judge_info) {
        throw new KilnError("Something went wrong.")
      }
      if (!sdg_session_config) {
        throw new KilnError("Something went wrong.")
      }
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot",
        {
          params: { path: { project_id, task_id } },
          body: {
            name,
            definition,
            properties,
            evaluate_full_trace,
            reviewed_examples,
            judge_info,
            sdg_session_config,
            task_description: task?.instruction || "",
            task_prompt_with_example,
            task_sample: few_shot_example
              ? {
                  input: few_shot_example.input,
                  output: few_shot_example.output,
                }
              : null,
          },
          signal,
        },
      )
      if (api_error) throw api_error
      spec_id = data?.id
      posthog.capture("create_spec", {
        spec_type: spec_type,
        with_copilot: true,
      })
    } else {
      // If there's an unsaved manual entry, don't include it - just pass null
      const task_sample =
        has_unsaved_manual_entry || !few_shot_example
          ? null
          : { input: few_shot_example.input, output: few_shot_example.output }

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec",
        {
          params: { path: { project_id, task_id } },
          body: {
            name,
            definition,
            properties,
            evaluate_full_trace,
            priority: 1,
            status: "active",
            task_sample,
          },
        },
      )
      if (api_error) throw api_error
      spec_id = data?.id
      posthog.capture("create_spec", {
        spec_type: spec_type,
        with_copilot: false,
      })
    }

    if (!spec_id) {
      throw new KilnError("Failed to create spec. Please try again.")
    }

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
  async function handle_create_spec_from_review() {
    error = null
    try {
      // Use full-page spinner for creating spec because it takes a while
      saving_spec = true
      current_state = "saving_with_copilot"

      // Store current reviewed examples
      const currentExamples = currentReviewedExamples()
      reviewed_examples = [...reviewed_examples, ...currentExamples]

      await saveSpec(
        property_values,
        true,
        reviewed_examples,
        new_copilot_abort_signal(),
      )
    } catch (e) {
      if (is_abort_error(e)) return
      error = createKilnError(e)
      current_state = "review"
    } finally {
      submitting = false
      saving_spec = false
    }
  }

  type SpecInfoForRefine = {
    spec_fields: Record<string, string>
    spec_field_current_values: Record<string, string>
  }

  function spec_info_for_refine(): SpecInfoForRefine {
    // Build spec info
    const spec_fields: Record<string, string> = {}
    const spec_field_current_values: Record<string, string> = {}

    for (const field of field_configs) {
      if (field.key === "tool_function_name") continue
      spec_fields[field.key] = field.description
      spec_field_current_values[field.key] = property_values[field.key] || ""
    }
    return {
      spec_fields,
      spec_field_current_values,
    }
  }

  // Handler for continuing to refine (feedback misaligned)
  async function handle_continue_to_refine() {
    try {
      error = null
      current_state = "refining"

      if (!task) {
        throw new KilnError("Task not loaded")
      }

      // Store current reviewed examples
      const currentExamples = currentReviewedExamples()
      reviewed_examples = [...reviewed_examples, ...currentExamples]

      // Build spec info
      const spec_info = spec_info_for_refine()

      // Convert reviewed examples to API format
      const examples_with_feedback = currentExamples.map((example) => ({
        user_agrees_with_judge:
          example.model_says_meets_spec === example.user_says_meets_spec,
        user_feedback: example.feedback,
        input: example.input,
        output: example.output,
        fails_specification: !example.user_says_meets_spec,
      }))

      if (examples_with_feedback.length === 0) {
        throw new KilnError(
          "No valid reviewed examples with feedback to refine spec.",
        )
      }

      const { data, error: api_error } = await client.POST(
        "/api/copilot/refine_spec",
        {
          body: {
            target_task_info: {
              task_prompt: task_prompt_with_example,
              task_input_schema: task_input_schema,
              task_output_schema: task_output_schema,
            },
            target_specification: {
              spec_fields: spec_info.spec_fields,
              spec_field_current_values: spec_info.spec_field_current_values,
            },
            examples_with_feedback,
          },
          signal: new_copilot_abort_signal(),
        },
      )

      if (api_error) {
        throw api_error
      }

      const processed = processProposedSpecEdits(
        data.new_proposed_spec_edits,
        property_values,
        data.not_incorporated_feedback || "",
      )
      refined_property_values = processed.refined_property_values
      suggested_edits = processed.suggested_edits
      not_incorporated_feedback = processed.not_incorporated_feedback

      posthog.capture("copilot_refine_spec_with_feedback", {
        spec_type: spec_type,
      })

      current_state = "refine"
    } catch (e) {
      if (is_abort_error(e)) return
      error = createKilnError(e)
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
      error = createKilnError(e)
      current_state = "refine"
    } finally {
      submitting = false
    }
  }

  // Handler for creating spec from refine (skip further review)
  async function handle_create_spec_from_refine() {
    error = null
    try {
      // Use full-page spinner for creating spec because it takes a while
      saving_spec = true
      current_state = "saving_with_copilot"
      await saveSpec(
        refined_property_values,
        true,
        reviewed_examples,
        new_copilot_abort_signal(),
      )
    } catch (e) {
      if (is_abort_error(e)) return
      error = createKilnError(e)
      current_state = "refine"
    } finally {
      submitting = false
      saving_spec = false
    }
  }

  async function get_question_set() {
    has_questioned_spec = true
    current_state = "questioning"

    const specification = buildSpecDefinition(spec_type, property_values)
    const { data, error: api_error } = await client.POST(
      "/api/copilot/question_spec",
      {
        body: {
          target_task_info: {
            task_prompt: task_prompt_with_example,
            task_input_schema,
            task_output_schema,
          },
          target_specification: specification,
        },
        signal: new_copilot_abort_signal(),
      },
    )
    if (api_error) {
      throw api_error
    }
    posthog.capture("copilot_question_spec", {
      spec_type: spec_type,
      num_questions: data.questions.length,
    })
    if (data.questions.length === 0) {
      await analyzeSpecForReview()
    } else {
      question_set = data
      current_state = "questions"
    }
  }

  async function handle_submit_question_answers(
    questions_and_answers: QuestionWithAnswer[],
  ) {
    error = null
    current_state = "refining"
    const spec_info = spec_info_for_refine()

    const request: SubmitAnswersRequest = {
      task_prompt: task_prompt_with_example,
      specification: {
        spec_fields: spec_info.spec_fields,
        spec_field_current_values: spec_info.spec_field_current_values,
      },
      questions_and_answers,
    }

    try {
      const { data, error: post_error } = await client.POST(
        "/api/copilot/refine_spec_with_question_answers",
        {
          body: request,
          signal: new_copilot_abort_signal(),
        },
      )

      if (post_error) {
        throw post_error
      }

      if (!data) {
        throw new KilnError(
          "Failed to refine spec with question answers. Please try again.",
        )
      }

      const processed = processProposedSpecEdits(
        data.new_proposed_spec_edits,
        property_values,
        data.not_incorporated_feedback || "",
      )
      refined_property_values = processed.refined_property_values
      suggested_edits = processed.suggested_edits
      not_incorporated_feedback = processed.not_incorporated_feedback

      posthog.capture("copilot_refine_spec_with_answers", {
        spec_type: spec_type,
        num_answers: questions_and_answers.length,
      })

      current_state = "refine"
    } catch (e) {
      if (is_abort_error(e)) return
      error = createKilnError(e)
      current_state = "questions"
    } finally {
      submitting = false
    }
  }

  // Page layout helpers based on current state
  function getPageTitle(state: BuilderState): string {
    switch (state) {
      case "create":
        return "Create Spec"
      case "questioning":
      case "questions":
        return "Copilot: Clarify Spec"
      case "analyzing_for_review":
      case "review":
        return "Copilot: Review and Refine"
      case "refining":
      case "refine":
        return "Copilot: Review Suggested Refinements"
      case "saving_with_copilot":
        return "Copilot: Creating Spec"
    }
  }

  function getPageSubtitle(state: BuilderState): string | undefined {
    switch (state) {
      case "create":
        return "A specification describes a behaviour to enforce or avoid for your task. Adding specs lets us measure and optimize quality."
      case "analyzing_for_review":
      case "refining":
      case "questioning":
      case "saving_with_copilot":
        return undefined
      case "questions":
        return "Reduce ambiguity of your spec."
      case "review":
        return "Improve your spec and judge with AI guidance."
      case "refine":
        return "Polish your spec to be analyzed further."
    }
  }

  // Helper to process proposed spec edits from API responses
  // Used by both handle_continue_to_refine and handle_submit_question_answers
  type ProposedSpecEdit = {
    spec_field_name: string
    proposed_edit: string
    reason_for_edit?: string | null
  }

  function processProposedSpecEdits(
    new_proposed_spec_edits: ProposedSpecEdit[] | null | undefined,
    current_property_values: Record<string, string | null>,
    feedback: string = "",
  ): {
    refined_property_values: Record<string, string | null>
    suggested_edits: Record<string, SuggestedEdit>
    not_incorporated_feedback: string
  } {
    const refined_values = { ...current_property_values }
    const edits: Record<string, SuggestedEdit> = {}

    if (new_proposed_spec_edits) {
      for (const edit of new_proposed_spec_edits) {
        refined_values[edit.spec_field_name] = edit.proposed_edit
        edits[edit.spec_field_name] = {
          proposed_value: edit.proposed_edit,
          reason_for_edit: edit.reason_for_edit || "",
        }
      }
    }

    return {
      refined_property_values: refined_values,
      suggested_edits: edits,
      not_incorporated_feedback: feedback,
    }
  }

  $: num_suggested_edits = Object.keys(suggested_edits).length

  function getPageClass(state: BuilderState): string {
    if (state === "review") return "max-w-[1400px]"
    if (state === "refine" && num_suggested_edits > 0) return "max-w-[1400px]"
    if (
      state === "analyzing_for_review" ||
      state === "refining" ||
      state === "questioning" ||
      state === "saving_with_copilot"
    )
      return ""
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
    sub_subtitle_link="https://docs.kiln.tech/docs/evals-and-specs"
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
    {#if loading || (saving_spec && current_state !== "saving_with_copilot")}
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
        {hide_full_trace_option}
        {full_trace_disabled}
        bind:error
        bind:submitting
        {is_prompt_building}
        {warn_before_unload}
        {project_id}
        {task_id}
        bind:few_shot_example
        bind:has_unsaved_manual_entry
        on:analyze_with_copilot={handle_analyze_with_copilot}
        on:create_without_copilot={handle_create_spec_without_copilot}
      />
    {:else if current_state === "analyzing_for_review"}
      <SpecAnalyzingAnimation />
    {:else if current_state === "questioning"}
      <QuestioningAnimation />
    {:else if current_state === "refining"}
      <RefiningAnimation />
    {:else if current_state === "saving_with_copilot"}
      <SavingAnimation />
    {:else if current_state === "review"}
      <ReviewExamples
        {name}
        {spec_type}
        {property_values}
        bind:review_rows
        bind:error
        bind:submitting
        {warn_before_unload}
        on:create_spec={() => handle_create_spec_from_review()}
        on:continue_to_refine={handle_continue_to_refine}
        on:create_spec_secondary={() => handle_create_spec_from_review()}
      />
    {:else if current_state === "refine"}
      <RefineSpec
        bind:name
        original_property_values={property_values}
        bind:refined_property_values
        {suggested_edits}
        {not_incorporated_feedback}
        {field_configs}
        bind:error
        bind:submitting
        {warn_before_unload}
        hide_secondary_button={reviewed_examples.length === 0}
        on:analyze_refined={handle_analyze_refined_spec}
        on:create_spec={() => handle_create_spec_from_refine()}
        on:create_spec_secondary={() => handle_create_spec_from_refine()}
      />
    {:else if current_state === "questions" && question_set}
      <Questions
        {name}
        {spec_type}
        {property_values}
        {question_set}
        on_submit={handle_submit_question_answers}
        bind:error
        bind:submitting
        {warn_before_unload}
      />
    {/if}
  </AppPage>
</div>
