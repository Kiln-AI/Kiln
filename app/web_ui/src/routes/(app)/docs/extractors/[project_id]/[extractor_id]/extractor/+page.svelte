<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type { ExtractorConfig } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { onMount } from "svelte"
  import { formatDate } from "$lib/utils/formatters"
  import Output from "../../../../../run/output.svelte"
  import Warning from "$lib/ui/warning.svelte"

  $: project_id = $page.params.project_id
  $: extractor_id = $page.params.extractor_id

  let loading: boolean = false
  let error: KilnError | null = null
  let extractor_config: ExtractorConfig | null = null

  onMount(async () => {
    await get_extractor_config()
  })

  async function get_extractor_config() {
    try {
      loading = true
      const { error: create_extractor_error, data } = await client.GET(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}",
        {
          params: {
            path: {
              project_id,
              extractor_config_id: extractor_id,
            },
          },
        },
      )

      if (create_extractor_error) {
        error = createKilnError(create_extractor_error)
        return
      }

      extractor_config = data
    } finally {
      loading = false
    }
  }

  async function archive_extractor_config() {
    const { error: archive_extractor_error } = await client.PATCH(
      "/api/projects/{project_id}/extractor_configs/{extractor_config_id}",
      {
        body: {
          is_archived: true,
        },
        params: {
          path: {
            project_id,
            extractor_config_id: extractor_id,
          },
        },
      },
    )

    if (archive_extractor_error) {
      throw createKilnError(archive_extractor_error)
    }

    await get_extractor_config()
  }

  async function unarchive_extractor_config() {
    const { error: unarchive_extractor_error } = await client.PATCH(
      "/api/projects/{project_id}/extractor_configs/{extractor_config_id}",
      {
        body: {
          is_archived: false,
        },
        params: {
          path: {
            project_id,
            extractor_config_id: extractor_id,
          },
        },
      },
    )

    if (unarchive_extractor_error) {
      throw createKilnError(unarchive_extractor_error)
    }

    await get_extractor_config()
  }

  function prompts(): Record<string, string | null> {
    return {
      Document: "" + (extractor_config?.properties?.prompt_document || "N/A"),
      Image: "" + (extractor_config?.properties?.prompt_image || "N/A"),
      Video: "" + (extractor_config?.properties?.prompt_video || "N/A"),
      Audio: "" + (extractor_config?.properties?.prompt_audio || "N/A"),
    }
  }
</script>

<AppPage
  title="Document Extractor"
  subtitle={loading ? "" : "Name: " + (extractor_config?.name || "Unknown")}
  action_buttons={[
    {
      label: extractor_config?.is_archived ? "Unarchive" : "Archive",
      primary: extractor_config?.is_archived,
      handler: () => {
        if (extractor_config?.is_archived) {
          unarchive_extractor_config()
        } else {
          archive_extractor_config()
        }
      },
    },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else}
    <div>
      {#if extractor_config?.is_archived}
        <Warning
          warning_message="This extractor is archived. You may unarchive it to use it again."
          large_icon={true}
          warning_color="warning"
          outline={true}
        />
      {/if}
      <div class="flex flex-col md:flex-row gap-16">
        <div class="grid grid-cols-1 gap-4">
          <div>
            <div class="text-xl font-bold">Extraction Prompts</div>
            <div class="text-sm text-gray-500 mt-1">
              These prompts are used by the model to extract content from each
              document type.
            </div>
          </div>
          {#each Object.entries(prompts()) as [name, prompt]}
            <div class="flex flex-col gap-2">
              <div class="font-medium">{name} Prompt</div>
              <Output raw_output={prompt || ""} />
            </div>
          {/each}
        </div>
        <div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
          <PropertyList
            title="Parameters"
            properties={[
              { name: "ID", value: extractor_config?.id || "N/A" },
              { name: "Name", value: extractor_config?.name || "N/A" },

              {
                name: "Type",
                value: extractor_config?.extractor_type || "N/A",
              },
              {
                name: "Model",
                value:
                  "" + (extractor_config?.properties?.model_name || "Unknown"),
              },
              {
                name: "Output Format",
                value: extractor_config?.output_format || "N/A",
              },
              {
                name: "Created At",
                value: formatDate(extractor_config?.created_at),
              },
              {
                name: "Created By",
                value: extractor_config?.created_by || "N/A",
              },
              {
                name: "Description",
                value: extractor_config?.description || "N/A",
              },
            ]}
          />
        </div>
      </div>
    </div>
    {#if error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {/if}
  {/if}
</AppPage>
