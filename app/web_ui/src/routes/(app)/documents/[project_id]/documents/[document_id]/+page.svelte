<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import type {
    Extraction,
    ExtractionWithOutput,
    KilnDocument,
  } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import {
    formatDate,
    formatSize,
  } from "../../../../../../lib/utils/formatters"
  import Dialog from "../../../../../../lib/ui/dialog.svelte"
  import PropertyList from "../../../../../../lib/ui/property_list.svelte"
  import DeleteDialog from "../../../../../../lib/ui/delete_dialog.svelte"
  import { isMacOS } from "../../../../../../lib/utils/platform"
  import { goto } from "$app/navigation"

  let document: KilnDocument | null = null
  let error: KilnError | null = null
  let loading = true
  let extractions: Extraction[] | null = null

  $: project_id = $page.params.project_id
  $: document_id = $page.params.document_id

  // dialog state
  $: dialog_extraction_id = ""
  let output_dialog: Dialog | null = null
  let dialog_loading = false
  let dialog_extraction: ExtractionWithOutput | null = null

  let download_document_url: string | null = null

  // whenever dialog_extraction_id changes, we need to call the API to fetch the output
  $: if (dialog_extraction_id) {
    get_extraction_output(dialog_extraction_id)
  }

  onMount(async () => {
    get_document()
    get_extractions()
    discover_download_document_url()
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

  async function get_extraction_output(extraction_id: string) {
    try {
      dialog_loading = true
      const { data: extraction_output_response, error: get_error } =
        await client.GET(
          "/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}",
          {
            params: {
              path: {
                project_id,
                document_id,
                extraction_id,
              },
            },
          },
        )

      if (get_error) {
        throw get_error
      }

      dialog_extraction = extraction_output_response
    } finally {
      dialog_loading = false
    }
  }

  async function discover_download_document_url() {
    const { data: serve_file_response, error: discover_error } =
      await client.GET(
        "/api/projects/{project_id}/documents/{document_id}/discover_serve_file",
        {
          params: {
            path: {
              project_id,
              document_id,
            },
          },
        },
      )

    if (discover_error) {
      throw createKilnError(discover_error)
    }

    download_document_url = serve_file_response.url
  }

  async function open_enclosing_folder() {
    try {
      loading = true
      const { error: open_error } = await client.POST(
        "/api/projects/{project_id}/documents/{document_id}/open_enclosing_folder",
        {
          params: {
            path: {
              project_id,
              document_id,
            },
          },
        },
      )
      if (open_error) {
        throw createKilnError(open_error)
      }
    } finally {
      loading = false
    }
  }

  export let delete_url: string | undefined = undefined
  let delete_dialog: DeleteDialog | null = null
  $: delete_url = `/api/projects/${project_id}/documents/${document_id}`
  function after_delete() {
    goto(`/documents/${project_id}/documents`)
  }
</script>

<AppPage
  title="Document"
  subtitle={`${document?.name} (${document?.original_file.filename})`}
  sub_subtitle={document?.description}
  no_y_padding
  action_buttons={[
    {
      icon: "/images/download.svg",
      href: download_document_url || "",
    },
    {
      icon: "/images/folder.svg",
      handler: () => {
        open_enclosing_folder()
      },
    },
    {
      icon: "/images/delete.svg",
      handler: () => delete_dialog?.show(),
      shortcut: isMacOS() ? "Backspace" : "Delete",
    },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if document}
    <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
      <div class="mt-4 mb-4">
        <PropertyList
          properties={[
            { name: "ID", value: document.id || "N/A" },
            { name: "Name", value: document.name },
            { name: "Original File", value: document.original_file.filename },
            { name: "Description", value: document.description },
            { name: "MIME Type", value: document.original_file.mime_type },
            { name: "Size", value: formatSize(document.original_file.size) },
            { name: "Kind", value: document.kind },
            { name: "Created At", value: formatDate(document.created_at) },
            { name: "Created By", value: document.created_by || "N/A" },
          ]}
          title="Properties"
        />
        <div class="mt-4 flex flex-row items-center gap-2">
          {#if document.tags}
            {#each document.tags as tag}
              <div
                class="badge bg-gray-200 py-3 px-3 max-w-full text-sm text-gray-500"
              >
                {tag}
              </div>
            {/each}
          {/if}
        </div>
      </div>
    </div>

    {#if extractions}
      <div class="block">
        <div class="block mt-4">
          <div class="text-2xl font-bold">Extractions</div>
          <div class="text-gray-500 text-sm">
            An extraction is the result of a document extractor running on a
            document.
          </div>
          <div class="mt-4 text-sm text-gray-500">
            {extractions.length}
            {extractions.length === 1 ? "extraction" : "extractions"}
          </div>
          <div class="text-sm text-gray-500">
            <table class="table table-sm">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Created At</th>
                  <th>Created By</th>
                  <th>Source</th>
                  <th>Extractor ID</th>
                  <th>Output</th>
                </tr>
              </thead>
              <tbody>
                {#each extractions as extraction}
                  <tr>
                    <td>{extraction.id}</td>
                    <td>{formatDate(extraction.created_at)}</td>
                    <td>{extraction.created_by}</td>
                    <td>{extraction.source}</td>
                    <td>
                      <a
                        href={`/documents/${project_id}/extractors/${extraction.extractor_config_id}/extractor`}
                        class="link link-primary flex flex-row items-center"
                        target="_blank"
                      >
                        <span class="font-mono text-gray-500">
                          {extraction.extractor_config_id}
                        </span>
                        <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
                        <svg
                          class="w-4 h-4 ml-2"
                          viewBox="0 0 24 24"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                          ><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g
                            id="SVGRepo_tracerCarrier"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                          ></g><g id="SVGRepo_iconCarrier">
                            <path
                              d="M5 12V6C5 5.44772 5.44772 5 6 5H18C18.5523 5 19 5.44772 19 6V18C19 18.5523 18.5523 19 18 19H12M8.11111 12H12M12 12V15.8889M12 12L5 19"
                              stroke="#464455"
                              stroke-linecap="round"
                              stroke-linejoin="round"
                            ></path>
                          </g></svg
                        >
                      </a>
                    </td>
                    <td>
                      <button
                        class="btn btn-primary"
                        on:click={() => {
                          dialog_extraction_id = extraction.id || ""
                          output_dialog?.show()
                        }}>View</button
                      >
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    {/if}
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Document</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={output_dialog}
  title="Extraction Output"
  close={() => {
    dialog_extraction_id = ""
    output_dialog?.hide()
  }}
>
  {#if dialog_loading}
    <div class="loading loading-spinner loading-lg"></div>
  {:else if dialog_extraction}
    <div class="text-sm text-gray-500 font-mono">
      <pre class="whitespace-pre-wrap">{dialog_extraction.output}</pre>
    </div>
  {/if}
</Dialog>

<DeleteDialog
  name={document?.name || "Document"}
  bind:this={delete_dialog}
  {delete_url}
  {after_delete}
/>
