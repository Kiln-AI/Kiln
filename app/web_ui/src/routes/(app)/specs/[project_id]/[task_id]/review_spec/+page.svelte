<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import type { SpecType } from "$lib/types"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import {
    createSpec,
    storeReviewedExamples,
    loadSpecFormData,
    saveSpecFormData,
    type ReviewedExample,
    type SpecFormData,
  } from "../spec_utils"
  import Warning from "$lib/ui/warning.svelte"
  import CheckCircleIcon from "$lib/ui/icons/check_circle_icon.svelte"
  import ExclaimCircleIcon from "$lib/ui/icons/exclaim_circle_icon.svelte"
  import SpecAnalyzingAnimation from "../spec_analyzing_animation.svelte"
  import { load_task } from "$lib/stores"
  import { buildDefinitionFromProperties } from "../select_template/spec_templates"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { client } from "$lib/api_client"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_error: KilnError | null = null
  let spec_loading = true

  let spec_type: SpecType = "desired_behaviour"
  let name = ""
  let property_values: Record<string, string | null> = {}
  let evaluate_full_trace = false

  let create_error: KilnError | null = null
  let submitting = false
  let complete = false

  $: submit_label = all_feedback_aligned ? "Create Spec" : "Next"
  $: submit_disabled = !all_feedback_aligned && !all_examples_reviewed

  type ReviewRow = {
    id: string
    input: string
    output: string
    model_says_meets_spec: boolean
    user_says_meets_spec: boolean | null
    feedback: string
  }

  let review_rows: ReviewRow[] = []
  let unexpandedRows: Record<string, boolean> = {}

  function toggleRowExpand(row_id: string) {
    unexpandedRows[row_id] = !unexpandedRows[row_id]
    unexpandedRows = unexpandedRows
  }

  function formatExpandedContent(data: string): string {
    try {
      const json = JSON.parse(data)
      return JSON.stringify(json, null, 2)
    } catch (_) {
      return data
    }
  }

  onMount(async () => {
    await load_spec_data()
  })

  let spec_definition: string = ""

  async function load_spec_data() {
    try {
      spec_loading = true
      spec_error = null

      const formData = loadSpecFormData(project_id, task_id)

      if (formData) {
        // Load the task to get instruction and schemas
        const task = await load_task(project_id, task_id)
        if (!task) {
          throw new Error("Failed to load task")
        }

        spec_type = formData.spec_type
        name = formData.name
        property_values = { ...formData.property_values }
        evaluate_full_trace = formData.evaluate_full_trace

        spec_definition = buildDefinitionFromProperties(
          spec_type,
          property_values,
        )

        // TODO: Create a few shot prompt instead of basic prompt
        // TODO: What should task input/output schemas be exactly? Especially for plaintext tasks?
        const { data, error } = await client.POST("/api/copilot/clarify_spec", {
          body: {
            task_prompt_with_few_shot: task.instruction,
            task_input_schema: task.input_json_schema
              ? JSON.stringify(task.input_json_schema)
              : "",
            task_output_schema: task.output_json_schema
              ? JSON.stringify(task.output_json_schema)
              : "",
            spec_rendered_prompt_template: spec_definition,
            num_samples_per_topic: 2,
            num_topics: 5,
            num_exemplars: 10,
          },
        })

        if (error) {
          throw error
        }

        if (!data) {
          throw new Error(
            "Failed to analyze spec for review. Please try again.",
          )
        }

        review_rows = data.examples_for_feedback.map((example, index) => ({
          id: String(index + 1),
          input: example.input,
          output: example.output,
          model_says_meets_spec: !example.exhibits_issue,
          user_says_meets_spec: null,
          feedback: "",
        }))

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

  function set_meets_spec(
    row_id: string,
    meets_spec: "yes" | "no",
    event: Event,
  ) {
    event.stopPropagation()
    review_rows = review_rows.map((row) => {
      if (row.id === row_id) {
        return {
          ...row,
          user_says_meets_spec: meets_spec === "yes",
          feedback: meets_spec === "yes" ? "" : row.feedback,
        }
      }
      return row
    })
  }

  function is_row_aligned(row: ReviewRow): boolean {
    if (row.user_says_meets_spec === null) return false
    return row.user_says_meets_spec === row.model_says_meets_spec
  }

  function should_show_feedback(row: ReviewRow): boolean {
    if (row.user_says_meets_spec === null) return false
    return !is_row_aligned(row)
  }

  function get_feedback_label(row: ReviewRow): string {
    if (row.user_says_meets_spec) {
      return "Describe why this meets the spec"
    } else {
      return "Describe why this does not meet the spec"
    }
  }

  $: all_feedback_aligned = review_rows.every((row) => {
    if (row.user_says_meets_spec === null) return false
    return row.user_says_meets_spec === row.model_says_meets_spec
  })

  $: all_examples_reviewed = review_rows.every((row) => {
    // All rows must have a meets_spec answer
    if (row.user_says_meets_spec === null) return false
    // If the answer is misaligned with the model, feedback is required
    if (should_show_feedback(row)) {
      return row.feedback.trim().length > 0
    }
    return true
  })

  /**
   * Collect reviewed examples from current review rows.
   * Only includes rows that have been explicitly reviewed (have a user_says_meets_spec value).
   */
  function collectReviewedExamples(): ReviewedExample[] {
    return review_rows
      .filter((row) => row.user_says_meets_spec !== null)
      .map((row) => ({
        input: row.input,
        output: row.output,
        user_says_meets_spec: row.user_says_meets_spec ?? false,
        feedback:
          row.user_says_meets_spec !== row.model_says_meets_spec
            ? row.feedback
            : null,
        model_says_meets_spec: row.model_says_meets_spec,
      }))
  }

  function handle_submit() {
    if (all_feedback_aligned) {
      // Store current reviewed examples (unions with any from previous cycles)
      const currentExamples = collectReviewedExamples()
      storeReviewedExamples(project_id, task_id, currentExamples)
      create_spec()
    } else {
      continue_to_refine()
    }
  }

  function continue_to_refine() {
    // Store the current reviewed examples (will be unioned with previous cycles)
    const currentExamples = collectReviewedExamples()
    storeReviewedExamples(project_id, task_id, currentExamples)

    // TODO: Call AI refinement API here with review_rows.filter(should_show_feedback)
    // Pass the rows where user feedback is misaligned with model decision
    // The API will return refined property_values which we'll store and pass to refine_spec

    // Store the current form data
    const formData: SpecFormData = {
      name,
      spec_type,
      property_values,
      evaluate_full_trace,
    }
    saveSpecFormData(project_id, task_id, formData)
    complete = true
    // Replace history so browser back goes to templates, not review
    goto(`/specs/${project_id}/${task_id}/refine_spec`, { replaceState: true })
  }

  async function create_spec() {
    try {
      create_error = null
      submitting = true

      // createSpec will read and save the accumulated reviewed examples
      const spec_id = await createSpec(
        project_id,
        task_id,
        name,
        spec_type,
        property_values,
        evaluate_full_trace,
      )

      complete = true
      // Replace history so browser back goes to templates
      goto(`/specs/${project_id}/${task_id}/${spec_id}`, { replaceState: true })
    } catch (error) {
      create_error = createKilnError(error)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Copilot: Review and Refine"
    subtitle={spec_loading
      ? undefined
      : `Improve your spec and judge with AI guidance.`}
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
    <FormContainer
      {submit_label}
      {submit_disabled}
      focus_on_mount={false}
      on:submit={handle_submit}
      bind:error={create_error}
      bind:submitting
      submit_visible={!spec_loading && !spec_error}
      warn_before_unload={!complete}
      compact_button={true}
    >
      {#if spec_loading}
        <div class="flex justify-center items-center h-full min-h-[200px]">
          <SpecAnalyzingAnimation />
        </div>
      {:else if spec_error}
        <div class="text-error text-sm">
          {spec_error.getMessage() || "An unknown error occurred"}
        </div>
      {:else}
        <Collapse title={name}>
          <div class="prose prose-sm max-w-none whitespace-pre-wrap">
            {spec_definition}
          </div>
        </Collapse>
        <Warning
          large_icon={true}
          warning_icon="info"
          outline={true}
          warning_color="primary"
          trusted={true}
          warning_message={`Review these examples to ensure Kiln understands the goal of this spec. This will ensure Kiln's synthetic data generation, evals and judge will work effectively.
For each row, select "Pass" if the example conforms to your spec and "Fail" if it does not.`}
        />
        <div class="flex flex-col gap-6">
          <div class="rounded-lg border">
            <table class="table">
              <thead>
                <tr>
                  <th class="w-1/2">Input</th>
                  <th class="w-1/2">Output</th>
                  <th class="whitespace-nowrap">
                    <div class="flex flex-row items-center gap-2">
                      <span>Meets Spec</span>
                      <span class="font-normal">
                        <InfoTooltip
                          tooltip_text="Whether the example conforms to your spec. If Kiln's judge analysis is inconsistent with your response, you will be asked to provide feedback to help Kiln refine the spec. Otherwise, you will see a green checkmark."
                        />
                      </span>
                    </div>
                  </th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {#each review_rows as row (row.id)}
                  <tr
                    on:click={() => toggleRowExpand(row.id)}
                    class="cursor-pointer"
                  >
                    <td class="py-2">
                      {#if !unexpandedRows[row.id]}
                        <pre class="whitespace-pre-wrap">{formatExpandedContent(
                            row.input,
                          )}</pre>
                      {:else}
                        <div class="truncate w-0 min-w-full">{row.input}</div>
                      {/if}
                    </td>
                    <td class="py-2">
                      {#if !unexpandedRows[row.id]}
                        <pre class="whitespace-pre-wrap">{formatExpandedContent(
                            row.output,
                          )}</pre>
                      {:else}
                        <div class="truncate w-0 min-w-full">{row.output}</div>
                      {/if}
                    </td>
                    <td class="py-2">
                      <div class="flex gap-1">
                        <button
                          class="btn btn-sm btn-outline hover:btn-success {row.user_says_meets_spec ===
                          true
                            ? 'btn-secondary'
                            : 'text-base-content/40'}"
                          on:click={(e) => set_meets_spec(row.id, "yes", e)}
                          tabindex="0">Pass</button
                        >
                        <button
                          class="btn btn-sm btn-outline hover:btn-warning {row.user_says_meets_spec ===
                          false
                            ? 'btn-secondary'
                            : 'text-base-content/40'}"
                          on:click={(e) => set_meets_spec(row.id, "no", e)}
                          tabindex="0">Fail</button
                        >
                      </div>
                    </td>
                    <td class="py-2">
                      <div class="w-5 h-5">
                        {#if row.user_says_meets_spec !== null}
                          {#if is_row_aligned(row)}
                            <div class="text-success w-full h-full">
                              <CheckCircleIcon />
                            </div>
                          {:else}
                            <div class="text-warning w-full h-full">
                              <ExclaimCircleIcon />
                            </div>
                          {/if}
                        {/if}
                      </div>
                    </td>
                  </tr>
                  {#if should_show_feedback(row)}
                    <tr on:click={(e) => e.stopPropagation()}>
                      <td colspan="4" class="bg-base-200 py-4">
                        <FormElement
                          label={get_feedback_label(row)}
                          description="Our judge analysis was inconsistent with your response. Please provide more detail to help refine the spec."
                          id="feedback-{row.id}"
                          inputType="textarea"
                          height="base"
                          bind:value={row.feedback}
                          optional={false}
                        />
                      </td>
                    </tr>
                  {/if}
                {/each}
              </tbody>
            </table>
          </div>
        </div>

        {#if !all_examples_reviewed && !submitting}
          <div class="flex justify-end">
            <Warning
              warning_color="warning"
              warning_message="Finish reviewing all examples before continuing."
              tight={true}
            />
          </div>
        {:else if all_feedback_aligned}
          <div class="flex justify-end">
            <Warning
              warning_color="success"
              warning_icon="check"
              warning_message="Our judge analysis was consistent with your responses. The spec is ready to be created."
              tight={true}
            />
          </div>
        {:else}
          <div class="flex justify-end">
            <Warning
              warning_color="error"
              warning_icon="exclaim"
              warning_message=""
              tight={true}
            />
          </div>
        {/if}
      {/if}
    </FormContainer>

    {#if !all_feedback_aligned && !spec_loading && !spec_error}
      <div class="flex flex-row gap-1 mt-2 justify-end">
        <span class="text-xs text-gray-500">or</span>
        <button
          class="link underline text-xs text-gray-500"
          disabled={submitting}
          on:click={create_spec}
        >
          {#if submitting}
            <span class="loading loading-spinner loading-xs"></span>
          {:else}
            Skip Review and Create Spec
          {/if}
        </button>
      </div>
    {/if}
  </AppPage>
</div>
