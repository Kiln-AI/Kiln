<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import type { ActionButton } from "../../../../../types"
  import Run from "../../../../../run/run.svelte"
  import Output from "../../../../../run/output.svelte"
  import {
    current_task,
    model_name,
    model_info,
    prompt_name_from_id,
    current_task_prompts,
  } from "$lib/stores"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { TaskRun } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import { isMacOS } from "$lib/utils/platform"

  $: run_id = $page.params.run_id
  $: task_id = $page.params.task_id
  $: project_id = $page.params.project_id
  // @ts-expect-error list_page is not a property of PageState
  $: list_page = ($page.state.list_page || []) as string[]

  // TODO: we need to remove task_id from the URL, or load it by ID. $current_task is a lie
  let run: TaskRun | null = null
  let loading = true
  let load_error: KilnError | null = null

  let model_props: Record<string, string | number | undefined> = {}
  $: {
    // Prompt ID previously was stored in the prompt_builder_name field
    let prompt_id = (
      run?.output?.source?.properties?.prompt_id ||
      run?.output?.source?.properties?.prompt_builder_name ||
      ""
    ).toString()

    let topic_path: string | undefined = undefined
    if (
      run?.input_source?.properties?.topic_path &&
      typeof run?.input_source?.properties?.topic_path === "string"
    ) {
      topic_path = run?.input_source?.properties?.topic_path?.replaceAll(
        ">>>>>",
        " > ",
      )
    }

    const model_id = run?.output?.source?.properties?.model_name
    model_props = Object.fromEntries(
      Object.entries({
        ID: run?.id || undefined,
        "Input Source":
          "" +
          run?.input_source?.type.charAt(0).toUpperCase() +
          run?.input_source?.type.slice(1),
        "Output Model": model_name(model_id, $model_info),
        "Model Provider": run?.output?.source?.properties?.model_provider,
        Prompt:
          prompt_id && prompt_name_from_id(prompt_id, $current_task_prompts),
        Cost: run?.usage?.cost ? `$${run?.usage?.cost.toFixed(6)}` : undefined,
        Tokens: run?.usage?.total_tokens ? run?.usage?.total_tokens : undefined,
        "Created By": run?.input_source?.properties?.created_by,
        "Created At": formatDate(run?.created_at),
        Topic: topic_path,
      }).filter(([_, value]) => value !== undefined && value !== ""),
    )
  }

  onMount(async () => {
    await load_run()
  })

  async function load_run() {
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
  }

  let delete_dialog: DeleteDialog | null = null
  let deleted: Record<string, boolean> = {}
  $: delete_url = `/api/projects/${project_id}/tasks/${task_id}/runs/${run_id}`
  function after_delete() {
    deleted[run_id] = true
  }

  function next_run() {
    const index = list_page.indexOf(run_id)
    if (index < list_page.length - 1) {
      const next_run_id = list_page[index + 1]
      load_run_by_id(next_run_id)
    }
  }

  function prev_run() {
    const index = list_page.indexOf(run_id)
    if (index > 0) {
      const prev_run_id = list_page[index - 1]
      load_run_by_id(prev_run_id)
    }
  }

  function load_run_by_id(new_run_id: string) {
    load_error = null
    run_id = new_run_id
    run = null
    goto(`/dataset/${project_id}/${task_id}/${run_id}/run`, {
      state: { list_page: list_page },
    })
    load_run()
  }

  let buttons: ActionButton[] = []
  $: {
    buttons = []
    if (!deleted[run_id]) {
      buttons.push({
        icon: "/images/delete.svg",
        handler: () => delete_dialog?.show(),
        shortcut: isMacOS() ? "Backspace" : "Delete",
      })
    }
    if (list_page.length > 1) {
      const index = list_page.indexOf(run_id)
      if (index !== -1) {
        buttons.push({
          icon: "/images/previous.svg",
          handler: prev_run,
          shortcut: "ArrowLeft",
          disabled: index === 0,
        })
        buttons.push({
          icon: "/images/next.svg",
          handler: next_run,
          shortcut: "ArrowRight",
          disabled: index === list_page.length - 1,
        })
      }
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Dataset Run"
    subtitle={run?.id ? `Run ID: ${run.id}` : undefined}
    action_buttons={buttons}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if deleted[run_id] === true}
      <div class="badge badge-error badge-lg p-4">Run Deleted</div>
    {:else if load_error}
      <div class="text-error">{load_error.getMessage()}</div>
    {:else if run && $current_task}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
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
              <div class="flex items-center text-gray-500 overflow-x-hidden">
                {value}
              </div>
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

<DeleteDialog
  name="Dataset Run"
  bind:this={delete_dialog}
  {delete_url}
  {after_delete}
/>
