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

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let instruction = ""
  let initial_instruction = ""
  let loading = true
  let save_error: KilnError | null = null
  let saving = false
  let warn_before_unload = false

  onMount(async () => {
    try {
      const task = await load_task(project_id, task_id)
      if (task) {
        instruction = task.instruction || ""
        initial_instruction = instruction
      }
      const pending = sessionStorage.getItem("pending_base_prompt")
      if (pending !== null) {
        instruction = pending
        sessionStorage.removeItem("pending_base_prompt")
      }
    } catch (e) {
      save_error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  $: if (!loading) {
    warn_before_unload = instruction !== initial_instruction
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
          body: { instruction },
        },
      )
      if (err) {
        throw err
      }
      const task = await load_task(project_id, task_id)
      current_task.set(task)
      warn_before_unload = false
      goto(`/prompts/${project_id}/${task_id}`)
    } catch (e) {
      save_error = createKilnError(e)
    } finally {
      saving = false
    }
  }
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
              description="The base prompt used by prompt generators (Basic, Few-shot, etc.)."
            />
          </FormContainer>
        </div>
      </div>
    {/if}
  </AppPage>
</div>
