<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { current_task, load_task } from "$lib/stores"
  import { page } from "$app/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"
  import type { Task } from "$lib/types"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let task: Task | null = null
  let instruction = ""
  let initial_instruction = ""
  let thinking_instruction = ""
  let initial_thinking_instruction = ""
  let loading = true
  let save_error: KilnError | null = null
  let loading_error: KilnError | null = null
  let saving = false
  let warn_before_unload = false

  onMount(async () => {
    try {
      task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Task not found")
      }
      instruction = task.instruction || ""
      initial_instruction = instruction
      thinking_instruction = task.thinking_instruction || ""
      initial_thinking_instruction = thinking_instruction
      const pending = sessionStorage.getItem("pending_base_prompt")
      if (pending !== null) {
        instruction = pending
        sessionStorage.removeItem("pending_base_prompt")
      }
    } catch (e) {
      loading_error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  $: if (!loading) {
    warn_before_unload =
      instruction !== initial_instruction ||
      thinking_instruction !== initial_thinking_instruction
  }

  async function save() {
    saving = true
    save_error = null
    try {
      const { error: err } = await client.PATCH(
        "/api/projects/{project_id}/task/{task_id}",
        {
          params: {
            path: { project_id, task_id },
          },
          body: { instruction, thinking_instruction },
        },
      )
      if (err) {
        throw err
      }
      current_task.set(task)
      warn_before_unload = false
      goto(`/prompts/${project_id}/${task_id}`)
    } catch (e) {
      save_error = createKilnError(e)
    } finally {
      saving = false
    }
  }

  $: task_has_requirements = task ? task.requirements.length > 0 : false
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Edit Task Prompt"
    subtitle="Update the base prompt for this task."
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${task_id}`,
      },
      {
        label: "Prompts",
        href: `/prompts/${project_id}/${task_id}`,
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div class="text-error text-sm">
        {loading_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <div class="max-w-[900px]">
        <div class="mt-6">
          <FormContainer
            submit_label="Save"
            on:submit={save}
            bind:error={save_error}
            bind:submitting={saving}
            {warn_before_unload}
          >
            <FormElement
              label="Prompt / Task Instructions"
              id="task_instruction"
              inputType="textarea"
              height="xl"
              bind:value={instruction}
              description="The base prompt used by prompt generators (Basic, Few-shot, etc.).{task_has_requirements
                ? ' Requirements from your task definition are appended to this.'
                : ''}"
            />
            <FormElement
              label="'Thinking' Instructions"
              inputType="textarea"
              id="thinking_instructions"
              optional={true}
              description="Instructions for how the model should 'think' about the task prior to answering. Used for chain of thought style prompting."
              info_description="Used when running a 'Chain of Thought' prompt. If left blank, a default 'think step by step' prompt will be used. Optionally customize this with your own instructions to better fit this task."
              bind:value={thinking_instruction}
            />
          </FormContainer>
        </div>
      </div>
    {/if}
  </AppPage>
</div>
