<script lang="ts">
  import type {
    AnswerOptionWithSelection,
    QuestionSet,
    QuestionWithAnswer,
  } from "$lib/types"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError } from "$lib/utils/error_handlers"

  export let question_set: QuestionSet
  export let on_submit: (
    questions_and_answers: QuestionWithAnswer[],
  ) => Promise<string | null>

  // Track the selected option for each question
  // "other" means the user selected the "Other" option
  // number means the index of the selected predefined option
  // null means no selection
  let selections: (number | "other" | null)[] = question_set.questions.map(
    () => null,
  )

  // Track the "Other" text for each question
  let other_texts: string[] = question_set.questions.map(() => "")

  let error: KilnError | null = null
  let submitting = false

  function validate(): string | null {
    for (let i = 0; i < question_set.questions.length; i++) {
      const selection = selections[i]
      if (selection === null) {
        return `Please answer question ${i + 1}`
      }
      if (selection === "other" && !other_texts[i].trim()) {
        return `Please provide feedback for question ${i + 1}`
      }
    }
    return null
  }

  function build_question_answers(): QuestionWithAnswer[] {
    return question_set.questions.map((question, q_index) => {
      const selection = selections[q_index]
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
        result.custom_answer = other_texts[q_index].trim()
      }

      return result
    })
  }

  async function handle_submit() {
    const validation_error = validate()
    if (validation_error) {
      error = new KilnError(validation_error, null)
      submitting = false
      return
    }

    error = null
    const questions_and_answers = build_question_answers()
    const result = await on_submit(questions_and_answers)
    if (result) {
      error = new KilnError(result, null)
    }
    submitting = false
  }

  function select_option(question_index: number, option_index: number) {
    selections[question_index] = option_index
    selections = selections
  }

  function select_other(question_index: number) {
    selections[question_index] = "other"
    selections = selections
  }
</script>

<div class="max-w-4xl">
  <FormContainer
    submit_label="Continue"
    on:submit={handle_submit}
    bind:error
    bind:submitting
    focus_on_mount={false}
  >
    <div class="flex flex-col gap-14">
      {#each question_set.questions as question, q_index}
        <div class="flex flex-col">
          <!-- Header row -->
          <h3 class="text-lg font-medium pb-2">
            Question {q_index + 1}: {question.question_title}
          </h3>

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
                    name="question-{q_index}"
                    class="radio mt-0.5"
                    checked={selections[q_index] === o_index}
                    on:change={() => select_option(q_index, o_index)}
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
                  name="question-{q_index}"
                  class="radio mt-0.5"
                  checked={selections[q_index] === "other"}
                  on:change={() => select_other(q_index)}
                />
                <div class="flex flex-col grow">
                  <span class="font-medium">Other</span>
                  <span
                    class="text-sm text-gray-500 {selections[q_index] ===
                    'other'
                      ? 'hidden'
                      : ''}">Provide a custom answer to this question.</span
                  >
                </div>
              </label>

              {#if selections[q_index] === "other"}
                <div class="ml-9">
                  <FormElement
                    id="other-text-{q_index}"
                    inputType="textarea"
                    bind:value={other_texts[q_index]}
                    label="Custom Answer"
                    placeholder="Enter a custom answer to the question."
                    height="medium"
                    aria_label="Custom answer for question {q_index + 1}"
                  />
                </div>
              {/if}
            </div>
          </div>
        </div>
      {/each}
    </div>
  </FormContainer>
</div>
