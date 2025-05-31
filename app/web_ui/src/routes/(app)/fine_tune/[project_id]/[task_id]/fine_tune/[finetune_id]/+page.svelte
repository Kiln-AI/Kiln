<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { FinetuneWithStatus } from "$lib/types"
  import { provider_name_from_id, load_available_models } from "$lib/stores"
  import { formatDate, data_strategy_name } from "$lib/utils/formatters"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Output from "../../../../../run/output.svelte"
  import EditDialog from "$lib/ui/edit_dialog.svelte"
  import { _ } from "svelte-i18n"

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
    info?: string
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
      { name: $_("finetune.details.kiln_id"), value: finetune_data.id },
      { name: $_("finetune.details.name"), value: finetune_data.name },
      {
        name: $_("finetune.details.description"),
        value: finetune_data.description,
      },
      { name: $_("finetune.details.provider"), value: provider_name },
      {
        name: $_("finetune.details.base_model"),
        value: finetune_data.base_model_id,
      },
      {
        name: provider_name + " " + $_("finetune.details.model_id"),
        value: format_model_id(
          finetune_data.fine_tune_model_id,
          finetune_data.provider,
        ),
        link: model_link(),
      },
      {
        name: provider_name + " " + $_("finetune.details.job_id"),
        value: format_provider_id(
          finetune_data.provider_id,
          finetune_data.provider,
        ),
        link: job_link(),
      },
      {
        name: $_("finetune.details.created_at"),
        value: formatDate(finetune_data.created_at),
      },
      {
        name: $_("finetune.details.created_by"),
        value: finetune_data.created_by,
      },
      {
        name: $_("finetune.details.type"),
        value: data_strategy_name(finetune_data.data_strategy),
        info: $_("finetune.details.type_info"),
      },
    ]
    properties = properties.filter((property) => !!property.value)
  }

  function job_link(): string | undefined {
    if (finetune?.finetune.provider === "openai") {
      return `https://platform.openai.com/finetune/${finetune.finetune.provider_id}`
    } else if (finetune?.finetune.provider === "together_ai") {
      return `https://api.together.ai/jobs/${finetune.finetune.provider_id}`
    } else if (finetune?.finetune.provider === "vertex") {
      const parts = finetune.finetune.provider_id?.split("/") || []
      const project = parts.length > 1 ? parts[1] : undefined
      let locationPath = parts.length > 2 ? parts.slice(2).join("/") : undefined
      if (!locationPath) {
        return undefined
      }
      locationPath = locationPath.replace("/tuningJobs/", "/tuningJob/")
      return `https://console.cloud.google.com/vertex-ai/studio/tuning/${locationPath}/detail?project=${project}`
    } else if (finetune?.finetune.provider === "fireworks_ai") {
      const url_id = finetune.finetune.provider_id?.split("/").pop()
      if (finetune.finetune.properties["endpoint_version"] === "v2") {
        // V2 style URL
        return `https://app.fireworks.ai/dashboard/fine-tuning/supervised/${url_id}`
      } else {
        // V1 style URL
        return `https://app.fireworks.ai/dashboard/fine-tuning/v1/${url_id}`
      }
    }
    return undefined
  }

  function model_link(): string | undefined {
    if (finetune?.finetune.provider === "together_ai") {
      return `https://api.together.ai/models/${finetune.finetune.fine_tune_model_id}`
    }
    return undefined
  }

  function format_provider_id(
    provider_id: string | null | undefined,
    provider: string,
  ): string {
    if (!provider_id) {
      return $_("finetune.details.unknown")
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
      return $_("finetune.details.not_completed")
    }
    if (provider === "fireworks_ai") {
      return model_id.split("/").pop() || model_id
    }
    return model_id
  }

  let edit_dialog: EditDialog | null = null
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={$_("finetune.details.title")}
    subtitle={finetune_loading
      ? undefined
      : `${$_("finetune.details.name")}: ${finetune?.finetune.name}`}
    action_buttons={[
      {
        label: $_("common.edit"),
        handler: () => {
          edit_dialog?.show()
        },
      },
      {
        label: $_("finetune.details.reload_status"),
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
          {$_("finetune.details.error_loading")}
        </div>
        <div class="text-error text-sm">
          {finetune_error?.getMessage() || $_("finetune.details.unknown_error")}
        </div>
      </div>
    {:else}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-10">
        <div class="grow flex flex-col gap-4">
          <div class="text-xl font-bold">
            {$_("finetune.details.details_section")}
          </div>
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
                {#if property.info}
                  <InfoTooltip tooltip_text={property.info} />
                {/if}
              </div>
            {/each}
          </div>

          {#if finetune.finetune.system_message || finetune.finetune.thinking_instructions}
            <div class="text-xl font-bold mt-8">
              {$_("finetune.details.training_prompt_section")}
            </div>
            {#if finetune.finetune.system_message}
              <div>
                <div class="text-sm font-bold text-gray-500 mb-2">
                  {$_("finetune.details.system_prompt_label")}
                </div>
                <Output raw_output={finetune.finetune.system_message} />
              </div>
            {/if}
            {#if finetune.finetune.thinking_instructions}
              <div>
                <div class="text-sm font-bold text-gray-500 mb-2">
                  {$_("finetune.details.thinking_instructions_label")}
                </div>
                <Output raw_output={finetune.finetune.thinking_instructions} />
              </div>
            {/if}
          {/if}
        </div>

        <div class="grow flex flex-col gap-4 min-w-[400px]">
          <div class="text-xl font-bold">
            {$_("finetune.details.status_section")}
          </div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-4 gap-x-4 text-sm 2xl:text-base"
          >
            <div class="flex items-center">{$_("finetune.details.status")}</div>
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
                  {$_("finetune.details.reload_status")}
                </button>
              {/if}
            </div>

            {#if finetune.status.message}
              <div class="flex items-center">
                {$_("finetune.details.status_message")}
              </div>
              <div class="flex items-center text-gray-500">
                {finetune.status.message}
              </div>
            {/if}

            {#if job_link()}
              <div class="flex items-center">
                {$_("finetune.details.job_dashboard")}
              </div>
              <div class="flex items-center text-gray-500">
                <a href={job_link()} target="_blank" class="btn btn-sm">
                  {provider_name_from_id(finetune.finetune.provider)}
                  {$_("finetune.details.dashboard")}
                </a>
              </div>
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  name={$_("finetune.details.title")}
  patch_url={`/api/projects/${project_id}/tasks/${task_id}/finetunes/${finetune_id}`}
  fields={[
    {
      label: $_("finetune.finetune_name_label"),
      description: $_("finetune.finetune_name_description"),
      api_name: "name",
      value: finetune?.finetune.name || "",
      input_type: "input",
    },
    {
      label: $_("finetune.finetune_description_label"),
      description: $_("finetune.finetune_description_description"),
      api_name: "description",
      value: finetune?.finetune.description || "",
      input_type: "textarea",
      optional: true,
    },
  ]}
/>
