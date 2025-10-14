<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { Task, TaskRun } from "$lib/types"
  import FormContainer from "../../../lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "../../../lib/utils/error_handlers"
  import { client } from "../../../lib/api_client"

  export let on_submit: (run: TaskRun) => void
  export let on_cancel: () => void

  export let project_id: string
  export let task: Task
  export let run: TaskRun
  export let repair_run: TaskRun
  export let repair_instructions: string

  function prettify_output(text: string) {
    if (task.output_json_schema) {
      try {
        return JSON.stringify(JSON.parse(text), null, 2)
      } catch (err) {
        return text
      }
    }
    return text
  }

  let repair_output_edited = prettify_output(repair_run.output.output) || ""

  let post_repair_error: KilnError | null = null
  let post_repair_submitting = false
  async function handle_submit() {
    repair_run = {
      ...repair_run,
      output: {
        ...repair_run.output,
        output: repair_output_edited,
        source: {
          type: "human",
          properties: {
            // the user name will be replaced with the actual user name on the server side
            created_by: "unknown",
          },
        },
      },
    }

    post_repair_error = null
    post_repair_submitting = true

    try {
      if (!repair_run) {
        throw new KilnError("No repair to edit", null)
      }
      if (!task.id || !run.id) {
        throw new KilnError(
          "This task run isn't saved. Enable Auto-save. You can't edit repairs for unsaved runs.",
          null,
        )
      }
      const {
        data, // only present if 2XX response
        error: fetch_error, // only present if 4XX or 5XX response
      } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/repair",
        {
          params: {
            path: {
              project_id: project_id,
              task_id: task.id,
              run_id: run.id,
            },
          },
          body: {
            repair_run: repair_run,
            evaluator_feedback: repair_instructions || "",
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      on_submit(data)
    } catch (err) {
      post_repair_error = createKilnError(err)
    } finally {
      post_repair_submitting = false
    }
  }

  function handle_cancel() {
    on_cancel()
  }
</script>

<div>
  <FormContainer
    submit_label="Save Repair (5 stars)"
    on:submit={handle_submit}
    submitting={post_repair_submitting}
  >
    <FormElement
      id={"repair_manual_output"}
      label="Manual Repair"
      info_description="Provide a improvement or correction to the task's output"
      inputType="textarea"
      height="large"
      bind:value={repair_output_edited}
    />

    {#if post_repair_error}
      <p class="text-error font-medium text-sm">
        Error Saving Repair<br />
        <span class="text-error text-xs font-normal">
          {post_repair_error.getMessage()}</span
        >
      </p>
    {/if}

    <button
      class="link text-gray-500 text-sm text-right"
      on:click={handle_cancel}>Cancel</button
    >
  </FormContainer>
</div>
