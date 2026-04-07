<script lang="ts">
  import type {
    AnswerOptionWithSelection,
    QuestionSet,
    QuestionWithAnswer,
    SpecType,
  } from "$lib/types"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import Dialog from "$lib/ui/dialog.svelte"
  import SpecPropertiesDisplay from "../spec_properties_display.svelte"

  export let name: string
  export let spec_type: SpecType
  export let property_values: Record<string, string | null>
  export let question_set: QuestionSet
  export let on_submit: (questions_and_answers: QuestionWithAnswer[]) => void
  export let on_skip: () => void
  export let error: KilnError | null
  export let submitting: boolean
  export let warn_before_unload: boolean

  // Track the selected option for each question (bound to parent to survive remounts)
  // "other" means the user selected the "Other" option
  // number means the index of the selected predefined option
  // null means no selection
  export let selections: (number | "other" | null)[] =
    question_set.questions.map(() => null)

  // Track the "Other" text for each question (bound to parent to survive remounts)
  export let other_texts: string[] = question_set.questions.map(() => "")

  // Track dismissed questions by index (bound to parent to survive remounts)
  export let dismissed: Set<number> = new Set()

  function dismiss_question(index: number) {
    dismissed.add(index)
    dismissed = dismissed
  }

  $: visible_questions = question_set.questions
    .map((q, i) => ({ question: q, original_index: i }))
    .filter((_, i) => !dismissed.has(i))

  $: all_dismissed =
    dismissed.size > 0 && dismissed.size === question_set.questions.length

  function validate(): string | null {
    for (let i = 0; i < visible_questions.length; i++) {
      const { original_index } = visible_questions[i]
      const selection = selections[original_index]
      if (selection === null) {
        return `Please answer question ${i + 1}`
      }
      if (selection === "other" && !other_texts[original_index].trim()) {
        return `Please provide feedback for question ${i + 1}`
      }
    }
    return null
  }

  function build_question_answers(): QuestionWithAnswer[] {
    return visible_questions.map(({ question, original_index }) => {
      const selection = selections[original_index]
      const is_other = selection === "other"

      const answer_options: AnswerOptionWithSelection[] =
        question.answer_options.map((option, o_index) => ({
          answer_title: option.answer_title,
          answer_description: option.answer_description,
          selected: !is_other && selection === o_index,
        }))

      const result: QuestionWithAnswer = {
        question_title: question.question_title,
        question_body: question.question_body,
        answer_options,
      }

      if (is_other) {
        result.custom_answer = other_texts[original_index].trim()
      }

      return result
    })
  }

  async function handle_submit() {
    if (all_dismissed) {
      await on_skip()
      return
    }

    const validation_error = validate()
    if (validation_error) {
      error = new KilnError(validation_error, null)
      submitting = false
      return
    }

    const questions_and_answers = build_question_answers()
    await on_submit(questions_and_answers)
  }

  function select_option(question_index: number, option_index: number) {
    selections[question_index] = option_index
    selections = selections
  }

  function select_other(question_index: number) {
    selections[question_index] = "other"
    selections = selections
  }

  let spec_details_dialog: Dialog | null = null
  function open_details_dialog() {
    spec_details_dialog?.show()
  }
</script>

<div class="max-w-4xl">
  <FormContainer
    submit_label="Continue"
    compact_button={true}
    on:submit={handle_submit}
    bind:error
    bind:submitting
    focus_on_mount={false}
    {warn_before_unload}
  >
    <div class="flex flex-col">
      <div class="font-medium">Answer Clarifying Questions</div>
      <div class="font-light text-gray-500 text-sm">
        Your answers to these questions will help Kiln refine your spec: <button
          class="link text-sm text-left text-gray-500 hover:text-gray-700"
          on:click={open_details_dialog}>{name}</button
        >.
      </div>
    </div>
    <div class="border-t" />
    <div class="flex flex-col gap-14">
      {#each visible_questions as { question, original_index }, display_index}
        <div class="flex flex-col">
          <!-- Header row -->
          <div class="flex items-start justify-between pb-2">
            <h3 class="text-lg font-medium">
              Question {display_index + 1}: {question.question_title}
            </h3>
            <button
              type="button"
              class="btn btn-ghost btn-sm text-gray-400 hover:text-gray-600"
              aria-label="Dismiss question"
              on:click={() => dismiss_question(original_index)}
            >
              <span class="text-xl">✕</span>
            </button>
          </div>

          <!-- Content row: body on left, options on right -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-8">
            <!-- Left column: Question body -->
            <p class="text-gray-500">{question.question_body}</p>

            <!-- Right column: Options -->
            <div class="flex flex-col gap-3">
              {#each question.answer_options as option, o_index}
                <label class="flex items-start gap-3 cursor-pointer group">
                  <input
                    type="radio"
                    name="question-{original_index}"
                    class="radio mt-0.5"
                    checked={selections[original_index] === o_index}
                    on:change={() => select_option(original_index, o_index)}
                  />
                  <div class="flex flex-col">
                    <span class="font-medium">{option.answer_title}</span>
                    <span class="text-sm text-gray-500"
                      >{option.answer_description}</span
                    >
                  </div>
                </label>
              {/each}

              <label class="flex items-start gap-3 cursor-pointer group">
                <input
                  type="radio"
                  name="question-{original_index}"
                  class="radio mt-0.5"
                  checked={selections[original_index] === "other"}
                  on:change={() => select_other(original_index)}
                />
                <div class="flex flex-col grow">
                  <span class="font-medium">Other</span>
                  <span
                    class="text-sm text-gray-500 {selections[original_index] ===
                    'other'
                      ? 'hidden'
                      : ''}">Provide a custom answer to this question.</span
                  >
                </div>
              </label>

              {#if selections[original_index] === "other"}
                <div class="ml-9">
                  <FormElement
                    id="other-text-{original_index}"
                    inputType="textarea"
                    bind:value={other_texts[original_index]}
                    label="Custom Answer"
                    placeholder="Enter a custom answer to the question."
                    height="medium"
                    aria_label="Custom answer for question {display_index + 1}"
                  />
                </div>
              {/if}
            </div>
          </div>
        </div>
      {/each}
      {#if all_dismissed}
        <div class="flex">
          <Warning
            warning_color="gray"
            tight={true}
            warning_icon="info"
            warning_message="All questions skipped. Click Continue to analyze your spec without refining further."
          />
        </div>
      {/if}
    </div>
  </FormContainer>
</div>

<Dialog
  bind:this={spec_details_dialog}
  title={`Spec: ${name}`}
  width="wide"
  action_buttons={[
    {
      label: "Close",
      isCancel: true,
    },
  ]}
>
  <SpecPropertiesDisplay {spec_type} properties={property_values} />
</Dialog>
