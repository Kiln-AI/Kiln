<script lang="ts">
  // TODO P0 - this page should be removed. The questions control should be used in specs.
  import AppPage from "../../app_page.svelte"
  import Questions from "../questions.svelte"
  import { client } from "$lib/api_client"
  import type {
    QuestionSet,
    QuestionWithAnswer,
    SubmitAnswersRequest,
    RefineSpecWithQuestionAnswersResponse,
  } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  let question_set: QuestionSet | null = null
  let error: KilnError | null = null
  let refine_response: RefineSpecWithQuestionAnswersResponse | null = null

  let submitted_question_request = false
  let task_prompt: string =
    "You are a helpful assistant that generates headlines for news articles when provided a news article."
  let spec_goal: string =
    "The headline should be a single sentence that captures the main idea of the news article."

  async function get_question_set() {
    submitted_question_request = true
    try {
      error = null
      const { data, error: get_error } = await client.POST(
        "/api/copilot/question_spec",
        {
          body: {
            task_prompt,
            specification: spec_goal,
          },
        },
      )
      if (get_error) {
        error = createKilnError(get_error)
        return
      }
      if (!data) {
        error = createKilnError("No question set returned")
        return
      }
      question_set = data
    } catch (e) {
      error = createKilnError(e)
    }
  }

  async function handle_submit_question_answers(
    questions_and_answers: QuestionWithAnswer[],
  ): Promise<string | null> {
    const request: SubmitAnswersRequest = {
      task_prompt,
      specification: {
        spec_fields: {
          spec_goal: "The main goal or objective for this specification",
        },
        spec_field_current_values: { spec_goal },
      },
      questions_and_answers,
    }

    error = null

    try {
      const { data, error: post_error } = await client.POST(
        "/api/refine_spec_with_question_answers",
        {
          body: request,
        },
      )

      if (post_error) {
        error = createKilnError(post_error)
        return error.getMessage()
      }
      if (!data) {
        error = createKilnError("No response returned")
        return error.getMessage()
      }

      refine_response = data
      return null
    } catch (e) {
      error = createKilnError(e)
      return error.getMessage()
    }
  }
</script>

<AppPage title="Questions Demo" subtitle="Demos of the spec questioner">
  {#if !submitted_question_request}
    <div class="max-w-xl flex flex-col gap-4">
      <div class="form-control w-full">
        <label class="label" for="task-prompt">
          <span class="label-text font-medium">Task Prompt</span>
        </label>
        <textarea
          id="task-prompt"
          class="textarea textarea-bordered w-full"
          rows="3"
          bind:value={task_prompt}
        ></textarea>
      </div>
      <div class="form-control w-full">
        <label class="label" for="spec-goal">
          <span class="label-text font-medium">Spec Goal</span>
        </label>
        <textarea
          id="spec-goal"
          class="textarea textarea-bordered w-full"
          rows="3"
          bind:value={spec_goal}
        ></textarea>
      </div>
      <button class="btn btn-primary mt-2" on:click={get_question_set}>
        Submit Questions
      </button>
    </div>
  {:else if refine_response}
    <div class="max-w-2xl flex flex-col gap-6">
      <div class="flex items-center gap-2">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-6 w-6 text-success"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fill-rule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clip-rule="evenodd"
          />
        </svg>
        <h2 class="text-xl font-semibold">Proposed Spec Edits</h2>
      </div>

      {#if refine_response.new_proposed_spec_edits.length === 0}
        <div class="text-base-content/70 italic">
          No edits proposed based on your answers.
        </div>
      {:else}
        <div class="flex flex-col gap-4">
          {#each refine_response.new_proposed_spec_edits as edit}
            <div class="card bg-base-200 shadow-sm">
              <div class="card-body gap-3">
                <div class="flex items-center gap-2">
                  <span class="badge badge-primary badge-outline">
                    {edit.spec_field_name}
                  </span>
                </div>

                <div class="flex flex-col gap-2">
                  <div class="text-sm font-medium text-base-content/70">
                    Proposed Edit
                  </div>
                  <div
                    class="bg-base-100 rounded-lg p-3 border border-base-300"
                  >
                    <p class="whitespace-pre-wrap">{edit.proposed_edit}</p>
                  </div>
                </div>

                <div class="flex flex-col gap-2">
                  <div class="text-sm font-medium text-base-content/70">
                    Reason
                  </div>
                  <p class="text-sm text-base-content/80 italic">
                    {edit.reason_for_edit}
                  </p>
                </div>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <button
        class="btn btn-outline btn-sm w-fit"
        on:click={() => {
          refine_response = null
          question_set = null
          submitted_question_request = false
        }}
      >
        Start Over
      </button>
    </div>
  {:else if question_set}
    <Questions {question_set} on_submit={handle_submit_question_answers} />
  {:else if error}
    <div class="text-error text-sm font-medium">
      {error.getMessage()}
    </div>
  {:else}
    <div class="text-sm font-medium flex items-center gap-2">
      <span class="loading loading-spinner"></span>
      Loading questions...
    </div>
  {/if}
</AppPage>
