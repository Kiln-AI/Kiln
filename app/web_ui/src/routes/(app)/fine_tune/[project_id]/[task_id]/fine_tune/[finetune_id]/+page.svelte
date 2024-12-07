<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { FinetuneWithStatus } from "$lib/types"
  import { provider_name_from_id, load_available_models } from "$lib/stores"
  import { formatDate } from "$lib/utils/formatters"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: finetune_id = $page.params.finetune_id
  $: running =
    finetune?.status.status === "pending" ||
    finetune?.status.status === "running"

  onMount(async () => {
    await load_available_models()
    get_fine_tune()
  })

  let finetune: FinetuneWithStatus | null = null
  let finetune_error: KilnError | null = null
  let finetune_loading = true

  const get_fine_tune = async () => {
    try {
      finetune_loading = true
      finetune_error = null
      finetune = null
      const { data: finetune_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              finetune_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      finetune = finetune_response
      build_properties()
    } catch (error) {
      finetune_error = createKilnError(error)
    } finally {
      finetune_loading = false
    }
  }

  type Property = {
    name: string
    value: string | null | undefined
    link?: string
  }
  let properties: Property[] = []
  function build_properties() {
    if (!finetune) {
      properties = []
      return
    }
    let finetune_data = finetune.finetune
    const provider_name = provider_name_from_id(finetune_data.provider)
    properties = [
      { name: "Kiln ID", value: finetune_data.id },
      { name: "Name", value: finetune_data.name },
      { name: "Description", value: finetune_data.description },
      { name: "Provider", value: provider_name },
      { name: "Base Model", value: finetune_data.base_model_id },
      {
        name: provider_name + " Model ID",
        value: format_model_id(
          finetune_data.fine_tune_model_id,
          finetune_data.provider,
        ),
      },
      {
        name: provider_name + " Job ID",
        value: format_provider_id(
          finetune_data.provider_id,
          finetune_data.provider,
        ),
        link: job_link(),
      },
      { name: "Created At", value: formatDate(finetune_data.created_at) },
      { name: "Created By", value: finetune_data.created_by },
    ]
    properties = properties.filter((property) => !!property.value)
  }

  function job_link(): string | undefined {
    if (finetune?.finetune.provider === "openai") {
      return `https://platform.openai.com/finetune/${finetune.finetune.provider_id}`
    } else if (finetune?.finetune.provider === "fireworks_ai") {
      const url_id = finetune.finetune.provider_id?.split("/").pop()
      return `https://fireworks.ai/dashboard/fine-tuning/${url_id}`
    }
    return undefined
  }

  function format_provider_id(
    provider_id: string | null | undefined,
    provider: string,
  ): string {
    if (!provider_id) {
      return "Unknown"
    }
    if (provider === "fireworks_ai") {
      return provider_id.split("/").pop() || provider_id
    }
    return provider_id
  }

  function format_model_id(
    model_id: string | null | undefined,
    provider: string,
  ): string {
    if (!model_id) {
      return "Not completed"
    }
    if (provider === "fireworks_ai") {
      return model_id.split("/").pop() || model_id
    }
    return model_id
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Fine Tune"
    subtitle={finetune_loading ? undefined : `Name: ${finetune?.finetune.name}`}
    action_buttons={[
      {
        label: "Reload Status",
        handler: () => {
          get_fine_tune()
        },
      },
    ]}
  >
    {#if finetune_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if finetune_error || !finetune}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">
          Error Loading Available Models and Datasets
        </div>
        <div class="text-error text-sm">
          {finetune_error?.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-10">
        <div class="grow flex flex-col gap-4">
          <div class="text-xl font-bold">Details</div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-4 gap-x-4 text-sm 2xl:text-base"
          >
            {#each properties as property}
              <div class="flex items-center">{property.name}</div>
              <div class="flex items-center text-gray-500">
                {#if property.link}
                  <a href={property.link} target="_blank" class="link">
                    {property.value}
                  </a>
                {:else}
                  {property.value}
                {/if}
              </div>
            {/each}
          </div>
        </div>

        <div class="grow flex flex-col gap-4">
          <div class="text-xl font-bold">Status</div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-4 gap-x-4 text-sm 2xl:text-base"
          >
            <div class="flex items-center">Status</div>
            <div class="flex items-center text-gray-500">
              {#if running}
                <span class="loading loading-spinner mr-2 h-[14px] w-[14px]"
                ></span>
              {/if}
              {finetune.status.status.charAt(0).toUpperCase() +
                finetune.status.status.slice(1)}
              {#if running}
                <button
                  class="link ml-2 text-xs font-medium"
                  on:click={get_fine_tune}
                >
                  Reload Status
                </button>
              {/if}
            </div>

            {#if finetune.status.message}
              <div class="flex items-center">Status Message</div>
              <div class="flex items-center text-gray-500">
                {finetune.status.message}
              </div>
            {/if}

            {#if job_link()}
              <div class="flex items-center">Job Dashboard</div>
              <div class="flex items-center text-gray-500">
                <a href={job_link()} target="_blank" class="btn btn-sm">
                  {provider_name_from_id(finetune.finetune.provider)} Dashboard
                </a>
              </div>
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>
