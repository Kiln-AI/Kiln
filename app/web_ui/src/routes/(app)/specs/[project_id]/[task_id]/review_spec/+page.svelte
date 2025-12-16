<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import type { SpecType } from "$lib/types"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createSpec } from "../spec_utils"
  import Warning from "$lib/ui/warning.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_error: KilnError | null = null
  let spec_loading = true

  let spec_type: SpecType = "desired_behaviour"
  let name = ""
  let property_values: Record<string, string | null> = {}

  let create_error: KilnError | null = null
  let submitting = false
  let complete = false
  let form_container: FormContainer

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
        spec_type = formData.spec_type || "desired_behaviour"
        name = formData.name || ""
        property_values = { ...formData.property_values }

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

  function should_show_feedback(row: ReviewRow): boolean {
    if (row.meets_spec === null) return false
    const user_says_meets_spec = row.meets_spec === "yes"
    const model_says_meets_spec = row.model_decision === "meets_spec"
    return user_says_meets_spec !== model_says_meets_spec
  }

  function get_feedback_label(row: ReviewRow): string {
    const user_says_meets_spec = row.meets_spec === "yes"
    if (user_says_meets_spec) {
      return "Describe why this meets the spec"
    } else {
      return "Describe why this does not meet the spec"
    }
  }

  $: rows_with_feedback = review_rows.filter(should_show_feedback)
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

  $: any_feedback_provided = review_rows.some((row) => {
    // All rows must have a meets_spec answer
    if (row.meets_spec === null) return false
    // If the answer is misaligned with the model, feedback is required
    if (should_show_feedback(row)) {
      return row.feedback.trim().length > 0
    }
    return false
  })

  async function continue_to_refine() {
    // Trigger validation first - if validation passes, do_continue_to_refine will be called via on:submit
    await form_container?.validate_and_submit()
  }

  function do_continue_to_refine() {
    // Store the review data and continue to refine_spec
    const formData = {
      name,
      spec_type,
      property_values,
      review_feedback: rows_with_feedback.map((row) => ({
        input: row.input,
        output: row.output,
        model_decision: row.model_decision,
        feedback: row.feedback,
      })),
    }
    sessionStorage.setItem(
      `spec_refine_${project_id}_${task_id}`,
      JSON.stringify(formData),
    )
    complete = true
    goto(`/specs/${project_id}/${task_id}/refine_spec`)
  }

  async function create_spec() {
    try {
      create_error = null
      submitting = true

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

<div class="max-w-[1400px]">
  <AppPage
    title="Review Spec"
    subtitle="Review these examples to ensure the spec accurately captures your goal"
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
        bind:this={form_container}
        submit_visible={false}
        focus_on_mount={false}
        on:submit={do_continue_to_refine}
        warn_before_unload={!complete}
      >
        <div class="flex flex-col gap-6">
          <div class="rounded-lg border">
            <table class="table table-fixed">
              <thead>
                <tr>
                  <th style="width: calc(50% - 100px)">Input</th>
                  <th style="width: calc(50% - 100px)">Output</th>
                  <th style="width: 200px">Meets Spec</th>
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
                  </tr>
                  {#if should_show_feedback(row)}
                    <tr on:click={(e) => e.stopPropagation()}>
                      <td colspan="3" class="bg-base-200 py-4">
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
      </FormContainer>

      <div class="flex flex-col gap-2 items-end">
        {#if create_error}
          <div class="text-error text-sm">
            {create_error.getMessage() || "An error occurred"}
          </div>
        {/if}
        {#if all_feedback_aligned}
          <button
            class="btn btn-primary"
            disabled={!all_feedback_aligned || submitting}
            on:click={create_spec}
          >
            {#if submitting}
              <span class="loading loading-spinner loading-sm"></span>
            {:else}
              Create Spec
            {/if}
          </button>
        {:else}
          {#if !all_examples_reviewed && any_feedback_provided && !submitting}
            <Warning
              warning_color="warning"
              warning_message="For best results, finish reviewing all examples before refining the spec."
              tight={true}
            />
          {/if}
          <button
            class="btn btn-primary"
            disabled={!any_feedback_provided || submitting}
            on:click={continue_to_refine}
          >
            Refine Spec with Feedback
          </button>
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
      </div>
    {/if}
  </AppPage>
</div>
