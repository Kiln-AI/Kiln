<script lang="ts">
  import PropertyList from "$lib/ui/property_list.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import type { Spec } from "$lib/types"
  import { client } from "$lib/api_client"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: spec_id = $page.params.spec_id

  let spec: Spec | null = null
  let spec_error: KilnError | null = null
  let spec_loading = true

  onMount(async () => {
    await load_spec()
  })

  async function load_spec() {
    try {
      spec_loading = true
      spec_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: { project_id, task_id, spec_id },
          },
        },
      )
      if (error) {
        throw error
      }
      spec = data
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      spec_loading = false
    }
  }
</script>

<AppPage
  title="Spec Details"
  subtitle={spec?.name || ""}
  breadcrumbs={[
    {
      label: "Specs",
      href: `/specs/${project_id}/${task_id}`,
    },
  ]}
>
  {#if spec_loading}
    <div class="flex justify-center items-center h-full">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if spec_error}
    <div class="text-error text-sm">
      {spec_error.getMessage() || "An unknown error occurred"}
    </div>
  {:else if !spec}
    <div class="text-error text-sm">
      Failed to load spec, please refresh the page and try again.
    </div>
  {:else}
    <PropertyList
      properties={[
        {
          name: "Name",
          value: spec.name,
        },
        {
          name: "Description",
          value: spec.description,
        },
        {
          name: "Type",
          value: spec.type,
        },
        {
          name: "Priority",
          value: spec.priority,
        },
        {
          name: "Status",
          value: spec.status,
        },
        {
          name: "Tags",
          value: spec.tags.length > 0 ? spec.tags.join(", ") : "None",
        },
        {
          name: "Eval ID",
          value: spec.eval_id || "None",
        },
      ]}
    />
  {/if}
</AppPage>
