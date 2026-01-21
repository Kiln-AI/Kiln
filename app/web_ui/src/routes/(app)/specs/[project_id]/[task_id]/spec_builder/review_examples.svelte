<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import CheckCircleIcon from "$lib/ui/icons/check_circle_icon.svelte"
  import ExclaimCircleIcon from "$lib/ui/icons/exclaim_circle_icon.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import SpecPropertiesDisplay from "../spec_properties_display.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import type { ReviewedExample } from "./spec_persistence"

  export let name: string
  export let spec_type: SpecType
  export let property_values: Record<string, string | null>

  type ReviewRow = ReviewedExample & { id: string }

  export let review_rows: ReviewRow[]
  export let error: KilnError | null
  export let submitting: boolean
  export let warn_before_unload: boolean

  let form_container: FormContainer

  const dispatch = createEventDispatcher<{
    create_spec: void
    continue_to_refine: void
    create_spec_secondary: void
  }>()

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

  function set_meets_spec(row_id: string, meets_spec: boolean, event: Event) {
    event.stopPropagation()
    review_rows = review_rows.map((row) => {
      if (row.id === row_id) {
        return {
          ...row,
          user_says_meets_spec: meets_spec,
          feedback: !meets_spec ? row.feedback : "",
        }
      }
      return row
    })
  }

  function is_row_aligned(row: ReviewRow): boolean {
    if (row.user_says_meets_spec === undefined) return false
    return row.user_says_meets_spec === row.model_says_meets_spec
  }

  function should_show_feedback(row: ReviewRow): boolean {
    if (row.user_says_meets_spec === undefined) return false
    return !is_row_aligned(row)
  }

  function get_feedback_empty_label(row: ReviewRow): string {
    if (row.user_says_meets_spec) {
      return "Describe why this meets the spec"
    } else {
      return "Describe why this does not meet the spec"
    }
  }

  $: all_feedback_aligned = review_rows.every((row) => {
    if (row.user_says_meets_spec === undefined) return false
    return row.user_says_meets_spec === row.model_says_meets_spec
  })

  $: all_examples_reviewed = review_rows.every((row) => {
    if (row.user_says_meets_spec === undefined) return false
    if (should_show_feedback(row)) {
      return row.feedback.trim().length > 0
    }
    return true
  })

  $: submit_label = all_feedback_aligned ? "Create Spec" : "Next"
  $: submit_disabled = !all_feedback_aligned && !all_examples_reviewed

  function handle_submit() {
    if (all_feedback_aligned) {
      dispatch("create_spec")
    } else {
      dispatch("continue_to_refine")
    }
  }

  let spec_details_dialog: Dialog | null = null
  function open_details_dialog() {
    spec_details_dialog?.show()
  }

  async function handle_secondary_click() {
    if (await form_container.validate_only()) {
      dispatch("create_spec_secondary")
    }
  }
</script>

<FormContainer
  bind:this={form_container}
  {submit_label}
  {submit_disabled}
  submit_data_tip={!all_examples_reviewed
    ? "Finish reviewing all examples before continuing."
    : undefined}
  focus_on_mount={false}
  on:submit={handle_submit}
  bind:error
  bind:submitting
  {warn_before_unload}
  compact_button={true}
>
  <div class="flex flex-col">
    <div class="font-medium">Review Data Examples</div>
    <div class="font-light text-gray-500 text-sm">
      Review these examples to ensure Kiln understands the goal of your spec: <button
        class="link text-sm text-left text-gray-500 hover:text-gray-700"
        on:click={open_details_dialog}
      >
        {name}</button
      >. For each row, select "Pass" if the example conforms to your spec and
      "Fail" if it does not. This will ensure Kiln's synthetic data generation,
      evals and judge will work effectively.
    </div>
  </div>
  <div class="flex flex-col gap-6">
    <div class="rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th class="w-2/5">Input</th>
            <th class="w-2/5">Output</th>
            <th class="whitespace-nowrap">
              <div class="flex flex-row items-center gap-2">
                <span>Meets Spec</span>
                <span class="font-normal">
                  <InfoTooltip
                    tooltip_text="Whether the example conforms to your spec. If Kiln's judge analysis is incorrect, you will be asked to provide feedback to help Kiln refine the spec."
                    position="top"
                  />
                </span>
              </div>
            </th>
            <th class="whitespace-nowrap">Judge Correct</th>
          </tr>
        </thead>
        <tbody>
          {#each review_rows as row (row.id)}
            <tr on:click={() => toggleRowExpand(row.id)} class="cursor-pointer">
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
                    on:click={(e) => set_meets_spec(row.id, true, e)}
                    tabindex="0">Pass</button
                  >
                  <button
                    class="btn btn-sm btn-outline hover:btn-warning {row.user_says_meets_spec ===
                    false
                      ? 'btn-secondary'
                      : 'text-base-content/40'}"
                    on:click={(e) => set_meets_spec(row.id, false, e)}
                    tabindex="0">Fail</button
                  >
                </div>
              </td>
              <td class="py-2">
                {#if row.user_says_meets_spec !== undefined}
                  <div class="flex items-center gap-1 justify-center">
                    {#if is_row_aligned(row)}
                      <div class="text-success w-5 h-5">
                        <CheckCircleIcon />
                      </div>
                    {:else}
                      <div class="text-warning w-5 h-5">
                        <ExclaimCircleIcon />
                      </div>
                    {/if}
                  </div>
                {/if}
              </td>
            </tr>
            {#if should_show_feedback(row)}
              <tr on:click={(e) => e.stopPropagation()}>
                <td colspan="4" class="bg-base-200 py-4">
                  <FormElement
                    label="Help us improve!"
                    description={`Our judge's analysis was incorrect, please provide a detailed description of why this example ${row.user_says_meets_spec ? "meets" : "does not meet"} the spec to help us improve our judge.`}
                    id="feedback-{row.id}"
                    inputType="textarea"
                    height="base"
                    bind:value={row.feedback}
                    optional={false}
                    placeholder={get_feedback_empty_label(row)}
                  />
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  {#if all_feedback_aligned}
    <div class="flex justify-end">
      <Warning
        warning_color="success"
        warning_icon="check"
        warning_message="Our judge analysis was consistent with your responses. Your spec is ready to be created."
        tight={true}
      />
    </div>
  {/if}
</FormContainer>

{#if !all_feedback_aligned}
  <div class="flex flex-row gap-1 mt-4 justify-end">
    <span class="text-sm text-gray-500">or</span>
    <button
      class="link underline text-sm text-gray-500"
      disabled={submitting}
      on:click={handle_secondary_click}
    >
      {#if submitting}
        <span class="loading loading-spinner loading-xs"></span>
      {:else}
        Skip Review and Create Spec
      {/if}
    </button>
  </div>
{/if}

<Dialog
  bind:this={spec_details_dialog}
  title={`Spec: ${name}`}
  action_buttons={[
    {
      label: "Close",
      isCancel: true,
    },
  ]}
>
  <SpecPropertiesDisplay {spec_type} properties={property_values} />
</Dialog>
