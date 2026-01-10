<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { goto } from "$app/navigation"
  import SavedRunConfigurationsDropdown from "$lib/ui/run_config_component/saved_run_configs_dropdown.svelte"
  import type { Task } from "$lib/types"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let token_budget: "light" | "medium" | "heavy" = "medium"
  let target_run_config_id: string | null = null

  let create_job_error: KilnError | null = null
  let create_job_loading = false
  let created_job_id: string | null = null

  let current_task: Task | null = null
  let task_loading = true

  onMount(async () => {
    await load_task()
  })

  async function load_task() {
    try {
      task_loading = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      current_task = data
    } catch (e) {
      create_job_error = createKilnError(e)
    } finally {
      task_loading = false
    }
  }

  async function create_gepa_job() {
    try {
      create_job_loading = true
      created_job_id = null

      if (!target_run_config_id || target_run_config_id === "custom") {
        throw new Error("Please select a saved run configuration")
      }

      const { data: response, error: post_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/start",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
          body: {
            token_budget,
            target_run_config_id,
          },
        },
      )

      if (post_error) {
        throw post_error
      }
      if (!response || !response.job_id) {
        throw new Error("Invalid response from server")
      }

      created_job_id = response.job_id

      goto(`/gepa/${project_id}/${task_id}/gepa_job/${created_job_id}`)
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        create_job_error = new KilnError("Could not create a GEPA job.", null)
      } else {
        create_job_error = createKilnError(e)
      }
    } finally {
      create_job_loading = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create a New GEPA Job"
    subtitle="Generate Eval Prompts and Augmented data."
    breadcrumbs={[{ label: "Tasks", href: `/tasks/${project_id}` }]}
  >
    {#if task_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if !current_task}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task</div>
        <div class="text-error text-sm">
          {create_job_error?.getMessage() || "Task not found"}
        </div>
      </div>
    {:else}
      <FormContainer
        submit_visible={true}
        submit_label="Start GEPA Job"
        on:submit={create_gepa_job}
        bind:error={create_job_error}
        bind:submitting={create_job_loading}
      >
        <div class="text-xl font-bold">Configure GEPA Job</div>

        <FormElement
          label="Token Budget"
          description="Select the token budget for this GEPA job. Light uses fewer tokens but is faster, Heavy uses more tokens but is more thorough."
          inputType="select"
          id="token_budget"
          select_options={[
            ["light", "Light"],
            ["medium", "Medium"],
            ["heavy", "Heavy"],
          ]}
          bind:value={token_budget}
        />

        <SavedRunConfigurationsDropdown
          title="Target Run Configuration"
          description="Select the run configuration to use for this GEPA job."
          {project_id}
          {current_task}
          bind:selected_run_config_id={target_run_config_id}
          run_page={false}
          auto_select_default={false}
        />
      </FormContainer>
    {/if}
  </AppPage>
</div>
