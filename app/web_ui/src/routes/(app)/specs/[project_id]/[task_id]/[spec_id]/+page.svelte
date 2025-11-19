<script lang="ts">
  import PropertyList from "$lib/ui/property_list.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import type { Spec } from "$lib/types"
  import { client } from "$lib/api_client"
  import {
    capitalize,
    formatPriority,
    formatSpecType,
  } from "$lib/utils/formatters"

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
  title="Spec{spec?.name ? `: ${spec.name}` : ''}"
  subtitle={spec?.type ? `Type: ${formatSpecType(spec.type)}` : ""}
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
    <div class="grid grid-cols-1 lg:grid-cols-[900px,500px] gap-12">
      <div class="flex flex-col gap-4">
        <div class="bg-base-200 rounded-lg p-6">
          <h3 class="text-lg font-medium mb-4">Definition</h3>
          <div class="prose prose-sm max-w-none whitespace-pre-wrap">
            {spec.definition}
          </div>
        </div>
      </div>

      <div class="flex flex-col gap-4">
        <PropertyList
          properties={[
            {
              name: "ID",
              value: spec.id ?? "None",
            },
            {
              name: "Type",
              value: formatSpecType(spec.type),
            },
            {
              name: "Priority",
              value: formatPriority(spec.priority),
            },
            {
              name: "Status",
              value: capitalize(spec.status),
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
      </div>
    </div>
  {/if}
</AppPage>
