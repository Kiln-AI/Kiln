<script lang="ts">
  // TODO P0 - this page should be removed. The questions control should be used in specs.
  import AppPage from "../../app_page.svelte"
  import Questions from "../questions.svelte"
  import { client } from "$lib/api_client"
  import type { QuestionSet, SubmitAnswersRequest } from "$lib/types"
  import { onMount } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  let question_set: QuestionSet | null = null
  let error: KilnError | null = null
  let submitted = false

  onMount(async () => {
    try {
      error = null
      const { data, error: get_error } = await client.GET(
        "/api/demo_question_set",
      )
      if (get_error) {
        error = createKilnError(get_error)
      }
      question_set = data
    } catch (e) {
      error = createKilnError(e)
    }
  })

  async function handle_submit(
    request: SubmitAnswersRequest,
  ): Promise<string | null> {
    console.info("Submitted answers:", request)
    // Demo just logs the request
    submitted = true
    return null
  }
</script>

<AppPage title="Questions Demo" subtitle="Demos a static set of questions">
  {#if submitted}
    <div class="text-center text-sm font-medium">
      [Demo] Questions submitted successfully.
    </div>
  {:else if question_set}
    <Questions {question_set} on_submit={handle_submit} />
  {:else if error}
    <div class="text-error text-sm font-medium">
      {error.getMessage()}
    </div>
  {:else}
    <div class="text-center text-sm font-medium">Loading...</div>
  {/if}
</AppPage>
