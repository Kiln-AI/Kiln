<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import type { ExtractorConfig } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"

  let extractor_config: ExtractorConfig | null = null
  let error: KilnError | null = null
  let loading = true

  $: project_id = $page.params.project_id
  $: extractor_config_id = $page.params.processor_id

  onMount(async () => {
    get_extractor_config()
  })

  async function get_extractor_config() {
    try {
      loading = true
      if (!project_id) {
        throw new Error("Project ID not set.")
      }
      const { data: extractor_config_response, error: get_error } =
        await client.GET(
          "/api/projects/{project_id}/extractor_configs/{extractor_config_id}",
          {
            params: {
              path: {
                project_id,
                extractor_config_id,
              },
            },
          },
        )
      if (get_error) {
        throw get_error
      }
      extractor_config = extractor_config_response
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        error = new KilnError(
          "Could not load dataset. It may belong to a project you don't have access to.",
          null,
        )
      } else {
        error = createKilnError(e)
      }
    } finally {
      loading = false
    }
  }

  async function run_extractor(extractor_config_id: string) {
    try {
      loading = true
      if (!project_id) {
        throw new Error("Project ID not set.")
      }
      const { error: run_error } = await client.GET(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}/run_extractor_config",
        {
          params: {
            path: {
              project_id,
              extractor_config_id,
            },
          },
        },
      )
      if (run_error) {
        throw run_error
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        error = new KilnError(
          "Could not run extractor. It may belong to a project you don't have access to.",
          null,
        )
      } else {
        error = createKilnError(e)
      }
    } finally {
      loading = false
    }
  }
</script>

<AppPage
  title={`Processor: ${extractor_config?.name || "unnamed"}`}
  sub_subtitle=""
  sub_subtitle_link="#"
  no_y_padding
  action_buttons={[
    {
      label: "Run Extractor",
      handler: () => {
        run_extractor(extractor_config_id)
      },
      primary: true,
    },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if extractor_config}
    <div class="my-4">
      <div class="text-2xl font-bold">{extractor_config.name}</div>
      <div class="text-sm text-gray-500">
        {extractor_config.description}
      </div>
      <div class="mt-4">
        <pre class="whitespace-pre-wrap font-mono">{JSON.stringify(
            extractor_config,
            null,
            2,
          )}</pre>
      </div>
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Processor</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>
