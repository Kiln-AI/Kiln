<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import type { ActionButton } from "../../../../../types"
  import Run from "../../../../../run/run.svelte"
  import Output from "../../../../../run/output.svelte"
  import {
    current_task,
    model_name,
    model_info,
    load_model_info,
    prompt_name_from_id,
    current_task_prompts,
    provider_name_from_id,
    load_available_models,
  } from "$lib/stores"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { TaskRun, StructuredOutputMode } from "$lib/types"
  import {
    formatDate,
    structuredOutputModeToString,
  } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { prompt_link } from "$lib/utils/link_builder"
  import type { ProviderModels, PromptResponse } from "$lib/types"
  import { getContext } from "svelte"
  import type { Writable } from "svelte/store"

  $: run_id = $page.params.run_id
  $: task_id = $page.params.task_id
  $: project_id = $page.params.project_id
  // @ts-expect-error list_page is not a property of PageState
  $: list_page = ($page.state.list_page || []) as string[]

  // We should remove task_id from the URL, or load it by ID. $current_task is a lie
  let run: TaskRun | null = null
  let loading = true
  let load_error: KilnError | null = null
  let see_all_properties = false

  function get_properties(
    run: TaskRun | null,
    current_task_prompts: PromptResponse | null,
    model_info: ProviderModels | null,
  ) {
    let properties = []

    if (run?.id) {
      properties.push({
        name: "ID",
        value: run.id,
      })
    }

    if (run?.input_source?.type) {
      properties.push({
        name: "Input Source",
        value:
          run.input_source.type.charAt(0).toUpperCase() +
          run.input_source.type.slice(1),
      })
    }

    const model_id = run?.output?.source?.properties?.model_name
    if (model_id) {
      properties.push({
        name: "Output Model",
        value: model_name(model_id, model_info),
      })
    }

    // Prompt ID previously was stored in the prompt_builder_name field
    let prompt_id = (
      run?.output?.source?.properties?.prompt_id ||
      run?.output?.source?.properties?.prompt_builder_name ||
      ""
    ).toString()
    if (prompt_id) {
      const prompt_name = prompt_name_from_id(prompt_id, current_task_prompts)
      if (prompt_name) {
        let link = prompt_link(project_id, task_id, prompt_id)
        properties.push({
          name: "Prompt",
          value: prompt_name,
          link: link,
        })
      }
    }

    if (run?.created_at) {
      properties.push({
        name: "Created At",
        value: formatDate(run.created_at),
      })
    }

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
    if (topic_path) {
      properties.push({
        name: "Topic",
        value: topic_path,
      })
    }

    return properties
  }

  function get_advanced_properties(run: TaskRun | null) {
    let properties = []

    if (run?.output?.source?.properties?.model_provider) {
      properties.push({
        name: "Model Provider",
        value: provider_name_from_id(
          String(run.output.source.properties.model_provider),
        ),
      })
    }

    if (run?.usage?.cost) {
      properties.push({
        name: "Cost",
        value: `$${run.usage.cost.toFixed(6)}`,
      })
    }

    if (run?.usage?.total_tokens) {
      properties.push({
        name: "Tokens",
        value: run.usage.total_tokens,
      })
    }

    if (run?.output?.source?.properties?.temperature !== undefined) {
      properties.push({
        name: "Temperature",
        value: run.output.source.properties.temperature,
      })
    }

    if (run?.output?.source?.properties?.top_p !== undefined) {
      properties.push({
        name: "Top P",
        value: run.output.source.properties.top_p,
      })
    }

    if (run?.output?.source?.properties?.structured_output_mode) {
      let mode = run.output.source.properties.structured_output_mode
      if (typeof mode === "string") {
        const json_mode = structuredOutputModeToString(
          mode as StructuredOutputMode,
        )
        if (json_mode) {
          properties.push({
            name: "JSON Mode",
            value: json_mode,
          })
        }
      }
    }

    if (run?.input_source?.properties?.created_by) {
      properties.push({
        name: "Created By",
        value: run.input_source.properties.created_by,
      })
    }

    return properties
  }

  onMount(async () => {
    await load_run()
    load_model_info()
    load_available_models()
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

  function isMac(): boolean {
    return (
      typeof window !== "undefined" &&
      navigator.platform.toUpperCase().indexOf("MAC") >= 0
    )
  }

  let buttons: ActionButton[] = []
  $: {
    buttons = []
    if (!deleted[run_id]) {
      buttons.push({
        icon: "/images/delete.svg",
        handler: () => delete_dialog?.show(),
        shortcut: isMac() ? "Backspace" : "Delete",
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

  // Fancy logic to maintain the search string when navigating back to the dataset page (filters, sorting, etc.)
  const lastPageUrl = getContext<Writable<URL | undefined>>("lastPageUrl")
  function get_breadcrumbs() {
    if (!$lastPageUrl) {
      return []
    }

    try {
      const referrerPath = $lastPageUrl.pathname

      // Check if the referrer path is /dataset/{project_id}/{task_id}
      // since we only want to breadcrumb back to that page
      const expectedPath = `/dataset/${$page.params.project_id}/${$page.params.task_id}`

      if (referrerPath === expectedPath) {
        return [
          {
            label: "Dataset",
            // Include the full URL with search params to a
            href: $lastPageUrl.pathname + $lastPageUrl.search,
          },
        ]
      }
    } catch (error) {
      console.warn("Failed to parse referrer URL:", error)
    }

    return []
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Dataset Run"
    subtitle={run?.id ? `Run ID: ${run.id}` : undefined}
    action_buttons={buttons}
    breadcrumbs={get_breadcrumbs()}
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
        <div class="w-72 2xl:w-96 flex-none flex flex-col">
          <PropertyList
            properties={[
              ...get_properties(run, $current_task_prompts, $model_info),
              ...(see_all_properties ? get_advanced_properties(run) : []),
            ]}
            title="Properties"
          />
          <button
            class="text-xs text-gray-500 underline text-left cursor-pointer bg-transparent border-none p-0 mt-4"
            on:click={() => (see_all_properties = !see_all_properties)}
          >
            {see_all_properties ? "See Less" : "See All"}
          </button>
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
