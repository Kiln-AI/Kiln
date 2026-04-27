<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import Output from "$lib/ui/output.svelte"

  type GuidePreviewSample = { input: string; output: string }

  export let preview_samples: GuidePreviewSample[] = []
  export let guide: string = ""
  export let error: KilnError | null = null
  export let submitting: boolean = false

  type ReviewedSample = {
    input: string
    output: string
    looks_good: boolean | undefined
  }

  let reviewed_samples: ReviewedSample[] = []
  $: reviewed_samples = preview_samples.map((s, i) => ({
    input: s.input,
    output: s.output,
    looks_good: reviewed_samples[i]?.looks_good,
  }))

  let general_feedback: string = ""

  // --- Edit guide dialog ---
  let edit_dialog: Dialog
  let editing_guide: string = ""

  function open_edit_dialog() {
    editing_guide = guide
    edit_dialog?.show()
  }

  function reset_guide() {
    editing_guide = guide
  }

  function save_guide_edit() {
    guide = editing_guide
    edit_dialog?.close()
    dispatch("regenerate")
  }

  $: guide_has_changes = editing_guide !== guide

  function set_looks_good(index: number, value: boolean, event: Event) {
    event.stopPropagation()
    reviewed_samples[index] = {
      ...reviewed_samples[index],
      looks_good: value,
    }
    reviewed_samples = reviewed_samples
  }

  $: all_reviewed = reviewed_samples.every((s) => s.looks_good !== undefined)
  $: all_look_good = all_reviewed && reviewed_samples.every((s) => s.looks_good)
  $: has_any_failed = reviewed_samples.some((s) => s.looks_good === false)
  $: needs_improvement_samples = reviewed_samples.filter(
    (s) => s.looks_good === false,
  )

  $: has_sufficient_feedback =
    needs_improvement_samples.length === 0 || general_feedback.trim().length > 0

  $: submit_disabled =
    !all_reviewed || (!all_look_good && !has_sufficient_feedback)

  $: submit_label =
    submit_disabled && !has_any_failed
      ? "Save Data Guide"
      : all_look_good
        ? "Save Data Guide"
        : "Refine with Feedback"

  const dispatch = createEventDispatcher<{
    refine: { feedback: string }
    save: void
    regenerate: void
  }>()

  function handle_submit() {
    if (all_look_good) {
      dispatch("save")
    } else {
      dispatch("refine", { feedback: general_feedback.trim() })
    }
  }
</script>

<FormContainer
  {submit_label}
  {submit_disabled}
  submit_data_tip={!all_reviewed
    ? "Review all examples before continuing."
    : !has_sufficient_feedback
      ? "Provide feedback for failed inputs."
      : undefined}
  on:submit={handle_submit}
  bind:error
  bind:submitting
  warn_before_unload={true}
  focus_on_mount={false}
  compact_button={true}
>
  <div class="flex flex-col">
    <div class="font-medium">Review Example Data</div>
    <div class="font-light text-gray-500 text-sm">
      Is synthetic data working as expected? Mark each example as "Pass" or
      "Fail". If any fail, provide feedback below and we'll refine the guide.
    </div>
  </div>
  <div class="flex flex-col gap-6">
    <div class="rounded-lg border">
      <table class="table table-fixed">
        <thead>
          <tr>
            <th>Input</th>
            <th>Output</th>
            <th style="width: 180px">Quality</th>
          </tr>
        </thead>
        <tbody>
          {#each reviewed_samples as sample, i}
            <tr>
              <td class="py-2">
                <pre
                  class="whitespace-pre-wrap break-words">{sample.input}</pre>
              </td>
              <td class="py-2">
                <pre
                  class="whitespace-pre-wrap break-words">{sample.output}</pre>
              </td>
              <td class="py-2">
                <div class="flex gap-1">
                  <button
                    class="btn btn-sm btn-outline hover:btn-success {sample.looks_good ===
                    true
                      ? 'btn-secondary'
                      : 'text-base-content/40'}"
                    on:click={(e) => set_looks_good(i, true, e)}
                    tabindex="0">Pass</button
                  >
                  <button
                    class="btn btn-sm btn-outline hover:btn-warning {sample.looks_good ===
                    false
                      ? 'btn-secondary'
                      : 'text-base-content/40'}"
                    on:click={(e) => set_looks_good(i, false, e)}
                    tabindex="0">Fail</button
                  >
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  {#if has_any_failed}
    <FormElement
      label="Feedback"
      description="Describe what's wrong with the failed inputs so we can refine the guide."
      id="general_feedback"
      inputType="textarea"
      height="base"
      bind:value={general_feedback}
      placeholder="e.g. Some inputs are missing the required 'patient_id' field, and all values should be more realistic."
    />
  {/if}

  <Collapse title="Task Data Guide" small={true}>
    <div class="flex flex-col gap-2">
      <Output raw_output={guide} show_border={true} background_color="white" />
      <div class="flex justify-end">
        <button
          class="btn btn-sm btn-outline"
          on:click={open_edit_dialog}
          type="button">Edit</button
        >
      </div>
    </div>
  </Collapse>

  {#if all_look_good}
    <div class="flex justify-end">
      <Warning
        warning_message="Synthetic data generation is working as expected. Your guide is ready to save."
        warning_color="success"
        warning_icon="check"
        tight
      />
    </div>
  {/if}
</FormContainer>

<!-- Edit Guide Dialog -->
<Dialog
  bind:this={edit_dialog}
  title="Edit Task Data Guide"
  sub_subtitle="Manually update the guide that will be used in synthetic data generation. Updating will regenerate new examples for review."
  width="wide"
>
  <FormContainer
    submit_label="Save and Continue"
    submit_disabled={!guide_has_changes}
    on:submit={save_guide_edit}
    warn_before_unload={guide_has_changes}
    compact_button={true}
  >
    <FormElement
      label="Data Guide"
      hide_label={true}
      id="edit_guide_text"
      inputType="textarea"
      height="xl"
      bind:value={editing_guide}
      inline_action={guide_has_changes
        ? { handler: reset_guide, label: "Reset" }
        : undefined}
    />
  </FormContainer>
</Dialog>
