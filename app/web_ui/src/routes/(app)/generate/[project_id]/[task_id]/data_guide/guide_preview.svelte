<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { GuideSample, GuideRule } from "./guide_setup_form.svelte"

  type GuidePreviewSample = { input: string; output: string }

  export let preview_samples: GuidePreviewSample[] = []
  export let guide_rules: GuideRule[] = []
  export let guide_examples: GuideSample[] = []
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
    needs_improvement_samples.length === 0 ||
    general_feedback.trim().length > 0

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
      Is synthetic data working as expected? Mark each input as "Pass" or
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

  {#if guide_rules.length > 0 || guide_examples.length > 0}
    <Collapse title="Current Data Guide" small={true}>
      {#if guide_examples.length > 0}
        <div class="mb-3">
          <div class="text-xs text-gray-500 uppercase font-medium mb-1">
            Examples ({guide_examples.length})
          </div>
          {#each guide_examples as example, i}
            <div class="text-sm text-gray-600 mb-1">
              <span class="font-medium">Example {i + 1}:</span>
              {example.input.slice(0, 80)}{example.input.length > 80
                ? "..."
                : ""}
            </div>
          {/each}
        </div>
      {/if}
      {#if guide_rules.length > 0}
        <div>
          <div class="text-xs text-gray-500 uppercase font-medium mb-1">
            Rules ({guide_rules.length})
          </div>
          {#each guide_rules as rule}
            <div class="text-sm text-gray-600 mb-1">
              <span class="font-medium">{rule.name}:</span>
              {rule.content.slice(0, 100)}{rule.content.length > 100
                ? "..."
                : ""}
            </div>
          {/each}
        </div>
      {/if}
    </Collapse>
  {/if}
</FormContainer>
