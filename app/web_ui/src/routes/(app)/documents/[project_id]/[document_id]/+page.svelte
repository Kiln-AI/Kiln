<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import type { Extraction, KilnDocument } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import FileIcon from "../fileicon.svelte"

  let document: KilnDocument | null = null
  let error: KilnError | null = null
  let loading = true
  let extractions: Extraction[] | null = null

  $: project_id = $page.params.project_id
  $: document_id = $page.params.document_id

  onMount(async () => {
    get_document()
    get_extractions()
  })

  async function get_document() {
    try {
      loading = true
      if (!project_id) {
        throw new Error("Project ID not set.")
      }
      const { data: document_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/documents/{document_id}",
        {
          params: {
            path: {
              project_id,
              document_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      document = document_response
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

  async function get_extractions() {
    try {
      loading = true
      const { data: extractions_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/documents/{document_id}/extractions",
        {
          params: {
            path: {
              project_id,
              document_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      extractions = extractions_response
    } finally {
      loading = false
    }
  }

  function format_size(size: number): string {
    if (size < 1024) {
      return size + " B"
    }
    if (size < 1024 * 1024) {
      return (size / 1024).toFixed(2) + " KB"
    }
    return (size / 1024 / 1024).toFixed(2) + " MB"
  }
</script>

<AppPage
  title="Documents"
  sub_subtitle="Read the Docs"
  sub_subtitle_link="#"
  no_y_padding
  action_buttons={[]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if document}
    <div class="mt-4 mb-4">
      <div class="flex flex-row items-center gap-2">
        <FileIcon kind={document.kind} class_name="w-16 h-16" />
        <div class="flex flex-col">
          <div class="text-2xl font-bold">{document.name}</div>
          <div class="text-sm text-gray-500">{document.description}</div>
        </div>
      </div>
      <div class="text-sm text-gray-500">
        {document.original_file.mime_type}
      </div>
      <div class="text-sm text-gray-500">
        {format_size(document.original_file.size)}
      </div>
      <div class="text-sm text-gray-500">{document.kind}</div>
      <div class="flex flex-row items-center gap-2">
        <div class="text-sm text-gray-500">
          {#if document.tags}
            {#each document.tags as tag}
              <div class="text-sm text-gray-500">{tag}</div>
            {/each}
          {/if}
        </div>
      </div>
    </div>
    {#if extractions}
      <div class="text-2xl font-bold">Extractions</div>
      <div class="text-sm text-gray-500">
        {extractions.length} extractions
      </div>
      {#each extractions as extraction}
        <div class="text-sm text-gray-500">
          <table class="table table-zebra">
            <thead>
              <tr>
                <th>ID</th>
                <th>Created At</th>
                <th>Created By</th>
                <th>Source</th>
                <th>Extractor Config ID</th>
                <th>Output</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{extraction.id}</td>
                <td>{extraction.created_at}</td>
                <td>{extraction.created_by}</td>
                <td>{extraction.source}</td>
                <td>{extraction.extractor_config_id}</td>
                <td>{extraction.output}</td>
              </tr>
            </tbody>
          </table>
        </div>
      {/each}
    {/if}
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Documents</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>
