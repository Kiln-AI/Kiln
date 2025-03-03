<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import EmptyFinetune from "./empty_finetune.svelte"
  import { client } from "$lib/api_client"
  import type { Finetune } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { formatDate } from "$lib/utils/formatters"
  import { provider_name_from_id, load_available_models } from "$lib/stores"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: is_empty = !finetunes || finetunes.length == 0

  let finetunes: Finetune[] | null = null
  let finetunes_error: KilnError | null = null
  let finetunes_loading = true

  onMount(async () => {
    await load_available_models()
    get_finetunes()
  })

  async function get_finetunes() {
    try {
      finetunes_loading = true
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      const { data: finetunes_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/finetunes",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
            query: {
              update_status: true,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      const sorted_finetunes = finetunes_response.sort((a, b) => {
        return (
          new Date(b.created_at || "").getTime() -
          new Date(a.created_at || "").getTime()
        )
      })
      finetunes = sorted_finetunes
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        finetunes_error = new KilnError(
          "Could not load finetunes. This task may belong to a project you don't have access to.",
          null,
        )
      } else {
        finetunes_error = createKilnError(e)
      }
    } finally {
      finetunes_loading = false
    }
  }

  const status_map: Record<string, string> = {
    pending: "Pending",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    unknown: "Unknown",
  }
  function format_status(status: string) {
    return status_map[status] || status
  }
</script>

<AppPage
  title="Fine Tune"
  subtitle="Fine-tune models for the current task."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.getkiln.ai/docs/fine-tuning-guide"
  action_buttons={is_empty
    ? []
    : [
        {
          label: "Create Fine Tune",
          href: `/fine_tune/${project_id}/${task_id}/create_finetune`,
          primary: true,
        },
      ]}
>
  {#if finetunes_loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if is_empty}
    <div class="flex flex-col items-center justify-center min-h-[60vh]">
      <EmptyFinetune {project_id} {task_id} />
    </div>
  {:else if finetunes}
    <div class="overflow-x-auto rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th> ID </th>
            <th> Name </th>
            <th> Provider</th>
            <th> Base Model</th>
            <th> Status </th>
            <th> Created At </th>
          </tr>
        </thead>
        <tbody>
          {#each finetunes as finetune}
            <tr
              class="hover cursor-pointer"
              on:click={() => {
                goto(
                  `/fine_tune/${project_id}/${task_id}/fine_tune/${finetune.id}`,
                )
              }}
            >
              <td> {finetune.id} </td>
              <td> {finetune.name} </td>
              <td> {provider_name_from_id(finetune.provider)} </td>
              <td> {finetune.base_model_id} </td>
              <td> {format_status(finetune.latest_status)} </td>
              <td> {formatDate(finetune.created_at)} </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if finetunes_error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Fine Tunes</div>
      <div class="text-error text-sm">
        {finetunes_error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>
