<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { agentInfo } from "$lib/agent"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  $: agentInfo.set({
    name: "Manual Data Entry",
    description: `Manually enter data for project ID ${project_id}, task ID ${task_id}.`,
  })

  let input_val = ""
  let output_val = ""
  let tags_val = ""
  let created_by_val = ""

  let submitting = false
  let error: KilnError | null = null
  let success_msg = ""

  async function handle_submit() {
    submitting = true
    error = null
    success_msg = ""
    try {
      const tags = tags_val
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0)

      const response = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/runs",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
          body: {
            input: input_val,
            output: output_val,
            tags: tags,
            input_source_type: "human",
            created_by: created_by_val || null,
          },
        },
      )

      if (response.error) {
        throw response.error
      }

      success_msg = "Successfully added sample to dataset."
      input_val = ""
      output_val = ""
      tags_val = ""
      // Keep created_by_val so the user doesn't have to re-type it for subsequent runs
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }

  $: dataset_link = `/dataset/${project_id}/${task_id}`
  $: breadcrumbs = [
    {
      label: "Dataset",
      href: dataset_link,
    },
    {
      label: "Add Data",
      href: `/dataset/${project_id}/${task_id}/add_data`,
    },
    {
      label: "Manual Entry",
      href: `/dataset/${project_id}/${task_id}/add_data/manual`,
    },
  ]
</script>

<AppPage title="Manual Data Entry" {breadcrumbs}>
  <div class="max-w-2xl mx-auto">
    {#if success_msg}
      <div
        class="alert alert-success shadow-lg mb-6 flex justify-between items-center"
      >
        <div class="flex items-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
            ><path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            /></svg
          >
          <span>{success_msg}</span>
        </div>
        <div class="flex gap-2">
          <button
            class="btn btn-sm btn-ghost"
            on:click={() => (success_msg = "")}>Dismiss</button
          >
          <a class="btn btn-sm btn-outline btn-neutral" href={dataset_link}
            >View Dataset</a
          >
        </div>
      </div>
    {/if}

    <div class="card bg-base-100 shadow-xl border border-base-200">
      <div class="card-body">
        <h2 class="card-title text-xl mb-4 font-bold">Add Labeled Sample</h2>
        <FormContainer
          submit_label="Add to Dataset"
          {submitting}
          {error}
          on:submit={handle_submit}
        >
          <FormElement
            label="Prompt (Input)"
            inputType="textarea"
            height="large"
            id="manual_input"
            bind:value={input_val}
            placeholder="Type or paste the input prompt here..."
          />

          <FormElement
            label="Response (Output)"
            inputType="textarea"
            height="large"
            id="manual_output"
            bind:value={output_val}
            placeholder="Type or paste the expected output response here..."
          />

          <FormElement
            label="Tags (Optional)"
            inputType="input"
            id="manual_tags"
            bind:value={tags_val}
            placeholder="e.g. train, test, custom_tag (comma separated)"
            optional={true}
          />

          <FormElement
            label="Created By (Optional)"
            inputType="input"
            id="manual_created_by"
            bind:value={created_by_val}
            placeholder="e.g. human, your name"
            optional={true}
          />
        </FormContainer>
      </div>
    </div>
  </div>
</AppPage>
