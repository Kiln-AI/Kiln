<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import Callout from "$lib/ui/callout.svelte"
  import Output from "$lib/ui/output.svelte"
  import ClampedText from "$lib/ui/clamped_text.svelte"

  type ReviewedSample = {
    input: string
    output: string
    looks_good: boolean | undefined
  }

  export let guide: string = ""
  export let initial_guide: string = guide
  export let error: KilnError | null = null
  export let submitting: boolean = false
  // Lifted to the parent so back/forward navigation can restore the user's
  // ratings + feedback for past review screens (each forward refine pushes a
  // new history entry; the parent snapshots these props before transitioning).
  export let reviewed_samples: ReviewedSample[] = []
  export let general_feedback: string = ""
  // Set true by the parent right before navigating away after a successful
  // save. Disables the unsaved-changes warn so the post-save goto doesn't
  // prompt the user.
  export let saved: boolean = false

  // True iff the user edited the guide via the Edit dialog after this
  // preview was generated. Drives the submit button label (Refine vs Save
  // Data Guide).
  $: guide_was_edited = guide !== initial_guide

  // Long input/output cells are clamped to 3 lines with a "See all" link;
  // clicking opens the full content in a dialog.
  let see_all_dialog: Dialog
  let see_all_title: string = ""
  let see_all_subtitle: string = ""
  let see_all_content: string = ""

  function show_full_text(title: string, subtitle: string, content: string) {
    see_all_title = title
    see_all_subtitle = subtitle
    see_all_content = content
    see_all_dialog?.show()
  }

  // Preview Data Guide collapse open state — used so the subtitle only shows
  // while expanded.
  let preview_collapse_open: boolean = false

  // --- Edit data guide dialog ---
  let edit_dialog: Dialog
  let editing_guide: string = ""

  function open_edit_dialog() {
    editing_guide = guide
    edit_dialog?.show()
  }

  // Reset reverts all edits made in this preview session, not just the
  // unsaved-in-dialog ones. Compares against initial_guide (the body when
  // this preview was generated) so reopening the dialog after a prior Save
  // still lets the user undo back to the original.
  function reset_guide() {
    editing_guide = initial_guide
  }
  $: guide_differs_from_initial = editing_guide !== initial_guide

  function save_guide_edit() {
    guide = editing_guide
    edit_dialog?.close()
  }

  // Verify Edit: same as Save, but immediately kicks off a preview
  // regeneration with the edited guide. Dispatches refine with empty
  // rated_samples + feedback so the parent's handle_refine takes the
  // no-metaprompter path (has_negative_feedback === false) — the user
  // explicitly chose to test the raw edit, not refine through ratings.
  function verify_edit_and_regenerate() {
    guide = editing_guide
    edit_dialog?.close()
    dispatch("refine", { feedback: "", rated_samples: [] })
  }

  $: guide_has_changes = editing_guide !== guide
  $: guide_is_empty = !editing_guide.trim()
  $: edit_buttons_disabled = !guide_has_changes || guide_is_empty

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

  // Generated samples (and any ratings/feedback/edits on top) are unsaved
  // work — back-navigation away from this screen loses them. Warn unless
  // the parent has flipped `saved` after a successful PUT.
  $: has_unsaved_user_work = !saved

  // Whenever the user changed something the LLM should react to (rated some
  // samples Needs Work, edited the guide text directly), switch the submit
  // button to Refine. Save Data Guide stays as the happy-path label when the
  // generated samples all looked good and the guide is unchanged.
  $: needs_refine = has_any_failed || guide_was_edited

  $: submit_disabled =
    !all_reviewed || (!all_look_good && !has_sufficient_feedback)

  $: submit_label = needs_refine ? "Continue" : "Save Data Guide"

  type RatedSample = { input: string; output: string; looks_good: boolean }

  const dispatch = createEventDispatcher<{
    refine: { feedback: string; rated_samples: RatedSample[] }
    save: void
  }>()

  function handle_submit() {
    if (!needs_refine) {
      dispatch("save")
    } else {
      const rated_samples: RatedSample[] = reviewed_samples
        .filter(
          (s): s is ReviewedSample & { looks_good: boolean } =>
            typeof s.looks_good === "boolean",
        )
        .map((s) => ({
          input: s.input,
          output: s.output,
          looks_good: s.looks_good,
        }))
      dispatch("refine", {
        feedback: general_feedback.trim(),
        rated_samples,
      })
    }
  }

  function handle_save_without_refining() {
    dispatch("save")
  }

  function scroll_to_feedback() {
    const el = document.getElementById("general_feedback")
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" })
      el.focus({ preventScroll: true })
    }
  }
</script>

<FormContainer
  {submit_label}
  {submit_disabled}
  submit_data_tip={!all_reviewed
    ? "Review all examples before continuing."
    : !has_sufficient_feedback
      ? "Provide feedback for examples that need work."
      : undefined}
  on:submit={handle_submit}
  bind:error
  bind:submitting
  warn_before_unload={has_unsaved_user_work && !submitting}
  focus_on_mount={false}
  compact_button={true}
>
  <Callout
    title="Is synthetic data working as expected?"
    description={`Mark each example as "Realistic" or "Needs Work" to determine if your guide generates high quality synthetic data. If some need work, we'll iterate to improve.`}
  >
    <div slot="icon">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
      <svg
        class="w-5 h-5"
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
    </div>
  </Callout>
  <div class="flex flex-col gap-6">
    <div class="rounded-lg border overflow-x-auto">
      <table class="table table-fixed">
        <thead>
          <tr>
            <th>Input</th>
            <th>Output</th>
            <th class="whitespace-nowrap" style="width: 220px; min-width: 220px"
              >Rating</th
            >
          </tr>
        </thead>
        <tbody>
          {#each reviewed_samples as sample, i}
            <tr>
              <td class="py-2">
                <ClampedText
                  content={sample.input}
                  on:see_all={() =>
                    show_full_text("Input", `Sample ${i + 1}`, sample.input)}
                />
              </td>
              <td class="py-2">
                <ClampedText
                  content={sample.output}
                  on:see_all={() =>
                    show_full_text("Output", `Sample ${i + 1}`, sample.output)}
                />
              </td>
              <td class="py-2">
                <div class="flex flex-col gap-1">
                  <div class="flex gap-1">
                    <button
                      type="button"
                      class="btn btn-sm btn-outline whitespace-nowrap hover:btn-success {sample.looks_good ===
                      true
                        ? 'btn-secondary'
                        : 'text-base-content/40'}"
                      on:click={(e) => set_looks_good(i, true, e)}
                      tabindex="0">Realistic</button
                    >
                    <div class="flex flex-col gap-1">
                      <button
                        type="button"
                        class="btn btn-sm btn-outline whitespace-nowrap hover:btn-warning {sample.looks_good ===
                        false
                          ? 'btn-secondary'
                          : 'text-base-content/40'}"
                        on:click={(e) => set_looks_good(i, false, e)}
                        tabindex="0">Needs Work</button
                      >
                      {#if sample.looks_good === false}
                        <div
                          class="flex text-xs text-gray-500 justify-end gap-1"
                        >
                          Tell us why <button
                            type="button"
                            class="text-xs text-gray-500 hover:text-gray-700"
                            on:click={scroll_to_feedback}>↓</button
                          >
                        </div>
                      {/if}
                    </div>
                  </div>
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
      description="Describe what needs work in the flagged examples so we can refine the guide."
      id="general_feedback"
      inputType="textarea"
      height="base"
      bind:value={general_feedback}
      placeholder="e.g. Some inputs are missing the required 'patient_id' field, and all values should be more realistic."
    />
  {/if}

  <Collapse
    title={guide_was_edited
      ? "Preview Data Guide (edited)"
      : "Preview Data Guide"}
    description={preview_collapse_open
      ? "Your Data Guide is a prompt that helps define how data is generated."
      : null}
    bind:open={preview_collapse_open}
    small={true}
  >
    <div class="flex flex-col gap-2">
      <div class="flex justify-end">
        <button
          class="btn btn-sm btn-outline"
          on:click={open_edit_dialog}
          type="button">Edit</button
        >
      </div>
      <Output raw_output={guide} show_border={true} />
    </div>
  </Collapse>

  {#if all_look_good && !guide_was_edited}
    <div class="flex justify-end">
      <Warning
        warning_message="Synthetic data generation is working as expected."
        warning_color="success"
        warning_icon="check"
        tight
      />
    </div>
  {:else if !all_reviewed}
    <div class="flex justify-end">
      <Warning
        warning_message="Please review all examples above."
        warning_color="warning"
        warning_icon="exclaim"
        tight
      />
    </div>
  {:else if has_any_failed && !has_sufficient_feedback}
    <div class="flex justify-end">
      <Warning
        warning_message="Please provide feedback about what needs work."
        warning_color="warning"
        warning_icon="exclaim"
        tight
      />
    </div>
  {/if}
</FormContainer>

{#if has_any_failed}
  <div class="flex flex-row gap-1 mt-4 justify-end">
    <span class="text-sm text-gray-500">or</span>
    <button
      class="link underline text-sm text-gray-500"
      disabled={submitting}
      on:click={handle_save_without_refining}
    >
      {#if submitting}
        <span class="loading loading-spinner loading-xs"></span>
      {:else}
        Save Without Refining Further
      {/if}
    </button>
  </div>
{/if}

<!-- Edit Data Guide Dialog -->
<!-- No warn_before_unload here — the outer review-samples FormContainer
     already registers a beforeNavigate handler. Duplicating the flag in a
     nested FormContainer caused the unsaved-changes confirm() to fire twice
     on navigation, hence the raw buttons below instead of a FormContainer. -->
<Dialog bind:this={edit_dialog} title="Edit Data Guide" width="wide">
  <div>
    <div class="flex flex-row items-center pb-[4px] min-h-[1.25rem]">
      <span class="grow"></span>
      {#if guide_differs_from_initial}
        <button
          type="button"
          class="link ml-4 text-xs text-gray-500 hover:text-gray-700"
          on:click|stopPropagation={reset_guide}
        >
          Reset
        </button>
      {/if}
    </div>
    <FormElement
      label="Data Guide"
      hide_label={true}
      id="edit_guide_text"
      inputType="textarea"
      height="xl"
      bind:value={editing_guide}
    />
  </div>

  <!-- Two equal columns side-by-side, each taking half the dialog width.
       Buttons stretch to fill their column (default flex cross-axis), so
       both end up the same width regardless of label length. Helper text
       wraps naturally within the column. -->
  <div class="grid grid-cols-2 gap-4 mt-6">
    <div class="flex flex-col gap-1">
      <button
        type="button"
        class="btn btn-sm btn-outline btn-primary"
        disabled={edit_buttons_disabled}
        on:click={save_guide_edit}
      >
        Save
      </button>
      <div class="text-xs text-gray-500">
        Edit will be combined with feedback in the next step.
      </div>
    </div>
    <div class="flex flex-col gap-1">
      <button
        type="button"
        class="btn btn-sm btn-outline btn-primary"
        disabled={edit_buttons_disabled}
        on:click={verify_edit_and_regenerate}
      >
        Verify Edit
      </button>
      <div class="text-xs text-gray-500">
        Generate new examples using only this edit.
      </div>
    </div>
  </div>
</Dialog>

<Dialog
  bind:this={see_all_dialog}
  title={see_all_title}
  sub_subtitle={see_all_subtitle}
  width="wide"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  <pre
    class="whitespace-pre-wrap break-words text-sm text-gray-600">{see_all_content}</pre>
</Dialog>
