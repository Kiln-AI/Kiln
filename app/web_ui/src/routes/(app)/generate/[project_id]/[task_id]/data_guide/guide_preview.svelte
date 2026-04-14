<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"

  type GuidePreviewSample = { input: string; output: string }

  export let preview_samples: GuidePreviewSample[] = []
  export let requirements: string = ""
  export let error: KilnError | null = null
  export let submitting: boolean = false

  type ReviewedSample = {
    input: string
    output: string
    looks_good: boolean | undefined
    feedback: string
  }

  let reviewed_samples: ReviewedSample[] = []
  $: reviewed_samples = preview_samples.map((s, i) => ({
    input: s.input,
    output: s.output,
    looks_good: reviewed_samples[i]?.looks_good,
    feedback: reviewed_samples[i]?.feedback ?? "",
  }))

  let general_feedback: string = ""

  function set_looks_good(index: number, value: boolean, event: Event) {
    event.stopPropagation()
    reviewed_samples[index] = {
      ...reviewed_samples[index],
      looks_good: value,
      feedback: value ? "" : reviewed_samples[index].feedback,
    }
    reviewed_samples = reviewed_samples
  }

  $: all_reviewed = reviewed_samples.every((s) => s.looks_good !== undefined)
  $: all_look_good = all_reviewed && reviewed_samples.every((s) => s.looks_good)
  $: has_any_failed = reviewed_samples.some((s) => s.looks_good === false)
  $: needs_improvement_samples = reviewed_samples.filter(
    (s) => s.looks_good === false,
  )

  // Feedback is sufficient if there's general feedback OR every failed example has per-example feedback
  $: has_sufficient_feedback =
    needs_improvement_samples.length === 0 ||
    general_feedback.trim().length > 0 ||
    needs_improvement_samples.every((s) => s.feedback.trim().length > 0)

  $: submit_label = all_look_good ? "Looks Good, Save" : "Refine with Feedback"
  $: submit_disabled =
    !all_reviewed || (!all_look_good && !has_sufficient_feedback)

  const dispatch = createEventDispatcher<{
    refine: { feedback: string }
    save: void
  }>()

  function handle_submit() {
    if (all_look_good) {
      dispatch("save")
    } else {
      const parts: string[] = []
      if (general_feedback.trim()) {
        parts.push(`General: ${general_feedback.trim()}`)
      }
      for (const sample of needs_improvement_samples) {
        if (sample.feedback.trim()) {
          const idx = reviewed_samples.indexOf(sample) + 1
          parts.push(`Example ${idx}: ${sample.feedback.trim()}`)
        }
      }
      dispatch("refine", { feedback: parts.join("\n") })
    }
  }
</script>

<FormContainer
  {submit_label}
  {submit_disabled}
  submit_data_tip={!all_reviewed
    ? "Review all examples before continuing."
    : !has_sufficient_feedback
      ? "Provide general feedback or per-example feedback for failed inputs."
      : undefined}
  on:submit={handle_submit}
  bind:error
  bind:submitting
  warn_before_unload={true}
  focus_on_mount={false}
  compact_button={true}
>
  <div class="flex flex-col">
    <div class="font-medium">Review Synthetic Inputs</div>
    <div class="font-light text-gray-500 text-sm">
      Review the generated inputs below. The output column shows what the task
      produces for reference. Mark each input as "Pass" or "Fail". For any that
      fail, describe what's wrong and we'll refine the guidance.
    </div>
  </div>
  <div class="flex flex-col gap-6">
    <div class="rounded-lg border">
      <table class="table table-fixed">
        <thead>
          <tr>
            <th>Input</th>
            <th>Output</th>
            <th style="width: 180px">Input Quality</th>
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
            {#if sample.looks_good === false}
              <tr on:click={(e) => e.stopPropagation()}>
                <td colspan="3" class="bg-base-200 py-4">
                  <FormElement
                    label="What's wrong with this input?"
                    description="Optional per-example feedback. You can also use the general feedback field below if multiple inputs are failing for the same reason."
                    id="feedback-{i}"
                    inputType="textarea"
                    height="base"
                    bind:value={sample.feedback}
                    optional={true}
                    placeholder="e.g. Input structure is wrong, missing required fields..."
                  />
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  {#if has_any_failed}
    <FormElement
      label="General Feedback"
      description="Describe issues that apply to multiple or all failed inputs. This will be combined with any per-example feedback above."
      id="general_feedback"
      inputType="textarea"
      height="base"
      bind:value={general_feedback}
      optional={true}
      placeholder="e.g. All inputs are missing the required 'patient_id' field, values should be more realistic..."
    />
  {/if}

  {#if all_look_good}
    <div class="flex justify-end">
      <div
        class="text-sm text-success flex items-center gap-1 font-medium bg-success/10 px-3 py-1.5 rounded-lg"
      >
        All inputs look good. Your guide is ready to save.
      </div>
    </div>
  {/if}

  {#if requirements}
    <Collapse title="Generation Guidance" description="Advanced" small={true}>
      <pre class="whitespace-pre-wrap break-words text-sm text-gray-600">{requirements}</pre>
    </Collapse>
  {/if}
</FormContainer>
