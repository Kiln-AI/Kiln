<script lang="ts">
  // TODO P0 - this page should be removed. The questions control should be used in specs.
  import AppPage from "../../app_page.svelte"
  import Questions from "../questions.svelte"
  import { client } from "$lib/api_client"
  import type { QuestionSet, SubmitAnswersRequest } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  let question_set: QuestionSet | null = null
  let error: KilnError | null = null
  let submitted_question_answers = false

  let submitted_question_request = false
  let task_prompt: string =
    "You are a helpful assistant that generates headlines for news articles when provided a news article."
  let specification: string =
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
            specification,
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
    request: SubmitAnswersRequest,
  ): Promise<string | null> {
    console.info("Submitted answers:", request)
    // Demo just logs the request
    submitted_question_answers = true
    return null
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
        <label class="label" for="specification">
          <span class="label-text font-medium">Specification</span>
        </label>
        <textarea
          id="specification"
          class="textarea textarea-bordered w-full"
          rows="3"
          bind:value={specification}
        ></textarea>
      </div>
      <button class="btn btn-primary mt-2" on:click={get_question_set}>
        Submit Questions
      </button>
    </div>
  {:else if submitted_question_answers}
    <div class="text-center text-sm font-medium">
      [Demo] Questions submitted successfully.
    </div>
  {:else if question_set}
    <Questions {question_set} on_submit={handle_submit_question_answers} />
  {:else if error}
    <div class="text-error text-sm font-medium">
      {error.getMessage()}
    </div>
  {:else}
    <div class="text-center text-sm font-medium">Loading...</div>
  {/if}
</AppPage>
