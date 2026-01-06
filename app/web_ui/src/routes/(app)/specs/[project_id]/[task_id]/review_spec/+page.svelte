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

  $: submit_label = all_feedback_aligned
    ? "Create Spec"
    : "Refine Spec with Feedback"
  $: submit_disabled = !all_feedback_aligned && !any_feedback_provided

  type ReviewRow = {
    id: string
    input: string
    output: string
    model_decision: "meets_spec" | "fails_spec"
    meets_spec: "yes" | "no" | null
    feedback: string
  }

  let review_rows: ReviewRow[] = []
  let expandedRows: Record<string, boolean> = {}

  function toggleRowExpand(row_id: string) {
    expandedRows[row_id] = !expandedRows[row_id]
    expandedRows = expandedRows
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
    // Wait 6 seconds to simulate loading time
    await new Promise((resolve) => setTimeout(resolve, 6000))

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
        property_values = { ...formData.property_values }
        evaluate_full_trace = formData.evaluate_full_trace

        // Generate mock review data (in a real implementation, this would come from an API)
        review_rows = [
          {
            id: "1",
            input: "User uploads a PDF document",
            output: "Document successfully processed",
            model_decision: "meets_spec",
            meets_spec: null,
            feedback: "",
          },
          {
            id: "2",
            input: "User tries to upload an invalid file",
            output: "Error: Invalid file format",
            model_decision: "fails_spec",
            meets_spec: null,
            feedback: "",
          },
          {
            id: "3",
            input: "User requests a summary of uploaded file",
            output: "Summary generated successfully",
            model_decision: "meets_spec",
            meets_spec: null,
            feedback: "",
          },
        ]

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
          meets_spec,
          feedback: meets_spec === "yes" ? "" : row.feedback,
        }
      }
      return row
    })
  }

  function is_row_aligned(row: ReviewRow): boolean {
    if (row.meets_spec === null) return false
    const user_says_meets_spec = row.meets_spec === "yes"
    const model_says_meets_spec = row.model_decision === "meets_spec"
    return user_says_meets_spec === model_says_meets_spec
  }

  function should_show_feedback(row: ReviewRow): boolean {
    if (row.meets_spec === null) return false
    return !is_row_aligned(row)
  }

  function get_feedback_label(row: ReviewRow): string {
    const user_says_meets_spec = row.meets_spec === "yes"
    if (user_says_meets_spec) {
      return "Describe why this meets the spec"
    } else {
      return "Describe why this does not meet the spec"
    }
  }

  $: all_feedback_aligned = review_rows.every((row) => {
    if (row.meets_spec === null) return false
    const user_says_meets_spec = row.meets_spec === "yes"
    const model_says_meets_spec = row.model_decision === "meets_spec"
    return user_says_meets_spec === model_says_meets_spec
  })

  $: all_examples_reviewed = review_rows.every((row) => {
    // All rows must have a meets_spec answer
    if (row.meets_spec === null) return false
    // If the answer is misaligned with the model, feedback is required
    if (should_show_feedback(row)) {
      return row.feedback.trim().length > 0
    }
    return true
  })

  /**
   * Collect reviewed examples from current review rows.
   * Only includes rows that have been explicitly reviewed (have a meets_spec value).
   */
  function collectReviewedExamples(): ReviewedExample[] {
    return review_rows
      .filter((row) => row.meets_spec !== null)
      .map((row) => ({
        input: row.input,
        output: row.output,
        meets_spec: row.meets_spec === "yes",
      }))
  }

  $: any_feedback_provided = review_rows.some((row) => {
    // All rows must have a meets_spec answer
    if (row.meets_spec === null) return false
    // If the answer is misaligned with the model, feedback is required
    if (should_show_feedback(row)) {
      return row.feedback.trim().length > 0
    }
    return false
  })

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
    goto(`/specs/${project_id}/${task_id}/refine_spec`)
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
      goto(`/specs/${project_id}/${task_id}/${spec_id}`)
    } catch (error) {
      create_error = createKilnError(error)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Review Spec"
    subtitle="Review these examples to ensure the spec accurately captures your goal by comparing your responses against our judge's."
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
        <SpecAnalyzingAnimation />
      </div>
    {:else if spec_error}
      <div class="text-error text-sm">
        {spec_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <FormContainer
        {submit_label}
        {submit_disabled}
        focus_on_mount={false}
        on:submit={handle_submit}
        bind:error={create_error}
        bind:submitting
        warn_before_unload={!complete}
      >
        <div class="flex flex-col gap-6">
          <div class="rounded-lg border">
            <table class="table">
              <thead>
                <tr>
                  <th class="w-1/2">Input</th>
                  <th class="w-1/2">Output</th>
                  <th class="whitespace-nowrap">Meets Spec</th>
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
                      {#if expandedRows[row.id]}
                        <pre class="whitespace-pre-wrap">{formatExpandedContent(
                            row.input,
                          )}</pre>
                      {:else}
                        <div class="truncate w-0 min-w-full">{row.input}</div>
                      {/if}
                    </td>
                    <td class="py-2">
                      {#if expandedRows[row.id]}
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
                          class="btn btn-sm btn-outline hover:btn-success {row.meets_spec ===
                          'yes'
                            ? 'btn-secondary'
                            : 'text-base-content/40'}"
                          on:click={(e) => set_meets_spec(row.id, "yes", e)}
                          tabindex="0">Yes</button
                        >
                        <button
                          class="btn btn-sm btn-outline hover:btn-warning {row.meets_spec ===
                          'no'
                            ? 'btn-secondary'
                            : 'text-base-content/40'}"
                          on:click={(e) => set_meets_spec(row.id, "no", e)}
                          tabindex="0">No</button
                        >
                      </div>
                    </td>
                    <td class="py-2">
                      <div class="w-5 h-5">
                        {#if row.meets_spec !== null}
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

        {#if !all_examples_reviewed && any_feedback_provided && !submitting}
          <div class="flex justify-center">
            <Warning
              warning_color="warning"
              warning_message="For best results, finish reviewing all examples before refining the spec."
              tight={true}
            />
          </div>
        {/if}
        {#if all_feedback_aligned}
          <div class="flex justify-center">
            <Warning
              warning_color="success"
              warning_icon="check"
              warning_message="Our judge analysis was consistent with your responses. The spec is ready to be created."
              tight={true}
            />
          </div>
        {/if}
      </FormContainer>

      {#if !all_feedback_aligned}
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
              Create Spec Without Refining Further
            {/if}
          </button>
        </div>
      {/if}
    {/if}
  </AppPage>
</div>
