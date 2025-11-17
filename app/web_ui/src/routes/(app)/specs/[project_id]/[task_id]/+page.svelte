<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { page } from "$app/stores"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { onMount } from "svelte"
  import Intro from "$lib/ui/intro.svelte"
  import type { Spec } from "$lib/types"
  import { formatDate, capitalize } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let specs: Spec[] | null = null
  let specs_error: KilnError | null = null
  let specs_loading = true

  $: is_empty = !specs || specs.length == 0

  onMount(async () => {
    await load_specs()
  })

  async function load_specs() {
    try {
      specs_loading = true
      specs_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (error) {
        throw error
      }
      specs = data
    } catch (error) {
      specs_error = createKilnError(error)
    } finally {
      specs_loading = false
    }
  }
</script>

<AppPage
  limit_max_width={true}
  title="Specs"
  subtitle="Define the specs you want your task to follow"
  sub_subtitle={is_empty ? undefined : "Read the Docs"}
  sub_subtitle_link="https://docs.kiln.tech/docs/evaluations"
  action_buttons={is_empty
    ? []
    : [
        {
          label: "New Spec",
          href: `/specs/${project_id}/${task_id}/create_spec`,
          primary: true,
        },
      ]}
>
  <div class="flex flex-col gap-4">
    {#if specs_loading}
      <div class="flex justify-center items-center h-full">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if specs_error}
      <div class="text-error text-sm">
        {specs_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else if is_empty}
      <div class="max-w-[300px] mx-auto flex flex-col gap-2 mt-[10vh]">
        <Intro
          title="Specs"
          description_paragraphs={[
            "Specs are used to define how you want your task to behave.",
          ]}
          action_buttons={[
            {
              label: "Define a Spec",
              href: `/specs/${project_id}/${task_id}/create_spec`,
              is_primary: true,
            },
          ]}
        />
      </div>
    {:else if specs}
      <div class="overflow-x-auto rounded-lg border">
        <table class="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>Type</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Created At</th>
            </tr>
          </thead>
          <tbody>
            {#each specs as spec}
              <tr
                class="hover cursor-pointer"
                on:click={() => {
                  goto(`/specs/${project_id}/${task_id}/${spec.id}`)
                }}
              >
                <td class="font-medium">{spec.name}</td>
                <td class="max-w-md truncate">{spec.description}</td>
                <td>
                  {spec.type
                    .replace(/_/g, " ")
                    .split(" ")
                    .map((word) => capitalize(word))
                    .join(" ")}
                </td>
                <td>{capitalize(spec.priority)}</td>
                <td>
                  {spec.status === "not_started"
                    ? "Not Started"
                    : spec.status === "in_progress"
                      ? "In Progress"
                      : capitalize(spec.status)}
                </td>
                <td class="text-sm text-gray-500">
                  {formatDate(spec.created_at)}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</AppPage>
