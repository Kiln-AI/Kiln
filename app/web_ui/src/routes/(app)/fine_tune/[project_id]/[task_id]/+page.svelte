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
  import { data_strategy_name } from "$lib/utils/formatters"
  import { _ } from "svelte-i18n"

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
          $_("finetune.details.could_not_load_finetunes"),
          null,
        )
      } else {
        finetunes_error = createKilnError(e)
      }
    } finally {
      finetunes_loading = false
    }
  }

  function format_status(status: string) {
    const statusKey = `finetune.details.status_values.${status}`
    return $_(`${statusKey}`) !== statusKey ? $_(`${statusKey}`) : status
  }
</script>

<AppPage
  title={$_("finetune.details.title")}
  subtitle={$_("finetune.details.subtitle")}
  sub_subtitle={$_("finetune.details.read_docs")}
  sub_subtitle_link="https://docs.getkiln.ai/docs/fine-tuning-guide"
  action_buttons={is_empty
    ? []
    : [
        {
          label: $_("finetune.details.create_fine_tune"),
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
            <th> {$_("finetune.details.table_headers.name")} </th>
            <th> {$_("finetune.details.table_headers.type")} </th>
            <th> {$_("finetune.details.table_headers.provider")}</th>
            <th> {$_("finetune.details.table_headers.base_model")}</th>
            <th> {$_("finetune.details.table_headers.status")} </th>
            <th> {$_("finetune.details.table_headers.created_at")} </th>
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
              <td> {finetune.name} </td>
              <td>
                {data_strategy_name(finetune.data_strategy)}
              </td>
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
      <div class="font-medium">
        {$_("finetune.details.error_loading_finetunes")}
      </div>
      <div class="text-error text-sm">
        {finetunes_error.getMessage() ||
          $_("finetune.details.unknown_error_occurred")}
      </div>
    </div>
  {/if}
</AppPage>
