<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import Run from "../../../../../run/run.svelte"
  import Output from "../../../../../run/output.svelte"
  import { current_task, model_name, model_info } from "$lib/stores"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { TaskRun } from "$lib/types"

  $: run_id = $page.params.run_id
  $: task_id = $page.params.task_id
  $: project_id = $page.params.project_id

  // TODO: we need to remove task_id from the URL, or load it by ID. $current_task is a lie
  let run: TaskRun | null = null
  let loading = true
  let load_error: KilnError | null = null

  let model_props: Record<string, string | number | undefined> = {}
  $: {
    model_props = Object.fromEntries(
      Object.entries({
        "Input Source":
          "" +
          run?.input_source?.type.charAt(0).toUpperCase() +
          run?.input_source?.type.slice(1),
        "Output Model": model_name(
          "" + run?.output?.source?.properties?.model_name,
          $model_info,
        ),
        "Model Provider": run?.output?.source?.properties?.model_provider,
        "Prompt Builder": run?.output?.source?.properties?.prompt_builder_name,
        "Created By": run?.input_source?.properties?.created_by,
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
      }).filter(([_, value]) => value !== undefined),
    )
  }

  onMount(async () => {
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}",
        {
          params: {
            path: { project_id, task_id, run_id: run_id },
          },
        },
      )
      if (error) {
        throw error
      }
      run = data
    } catch (error) {
      if (error instanceof Error && error.message.includes("Load failed")) {
        load_error = new KilnError(
          "Could not load run. It may belong to a project you don't have access to.",
          null,
        )
      } else {
        load_error = createKilnError(error)
      }
    } finally {
      loading = false
    }
  })

  let deleted = false
  async function deleteRun() {
    if (
      !confirm(
        "Are you sure you want to delete this run?\n\nThis action cannot be undone.",
      )
    ) {
      return
    }
    try {
      loading = true
      await client.DELETE(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              run_id,
            },
          },
        },
      )
      deleted = true
    } catch (error) {
      load_error = createKilnError(error)
    } finally {
      loading = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Dataset Run"
    subtitle={run?.id ? `Run ID: ${run.id}` : undefined}
    action_buttons={deleted
      ? []
      : [{ label: "Delete Run", handler: deleteRun }]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if deleted}
      <div class="badge badge-error badge-lg p-4">Run Deleted</div>
    {:else if load_error}
      <div class="text-error">{load_error.getMessage()}</div>
    {:else if run && $current_task}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-10">
        <div class="grow">
          <div class="text-xl font-bold mb-4">Input</div>
          <Output raw_output={run.input} />
        </div>
        <div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
          <div class="text-xl font-bold">Parameters</div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base"
          >
            {#each Object.entries(model_props) as [key, value]}
              <div class="flex items-center">{key}</div>
              <div class="flex items-center text-gray-500">{value}</div>
            {/each}
          </div>
        </div>
      </div>
      <Run initial_run={run} task={$current_task} {project_id} />
    {:else}
      <div class="text-gray-500 text-lg">Run not found</div>
    {/if}
  </AppPage>
</div>
