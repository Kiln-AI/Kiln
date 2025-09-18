<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { base_url, client } from "$lib/api_client"
  import type { ExtractionSummary, KilnDocument } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { formatDate, formatSize } from "$lib/utils/formatters"
  import Dialog from "$lib/ui/dialog.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import { isMacOS } from "$lib/utils/platform"
  import { goto } from "$app/navigation"
  import Output from "../../../../run/output.svelte"
  import { capitalize } from "$lib/utils/formatters"
  import TagDropdown from "../../../../../../lib/ui/tag_dropdown.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  let initial_document: KilnDocument | null = null
  let updated_document: KilnDocument | null = null
  $: document = updated_document || initial_document
  let error: KilnError | null = null
  let loading = true
  let results: ExtractionSummary[] | null = null

  $: project_id = $page.params.project_id
  $: document_id = $page.params.document_id

  // dialog state
  let output_dialog: Dialog | null = null
  let dialog_extraction: ExtractionSummary | null = null

  $: download_document_url = `${base_url}/api/projects/${project_id}/documents/${document_id}/download`

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
      updated_document = document_response
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
      results = extractions_response
    } finally {
      loading = false
    }
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

  let delete_document_dialog: DeleteDialog | null = null
  $: delete_document_url = `/api/projects/${project_id}/documents/${document_id}`
  function after_document_delete() {
    goto(`/docs/library/${project_id}`)
  }

  let delete_extraction_id: string | null = null
  let delete_extraction_dialog: DeleteDialog | null = null
  $: delete_extraction_url = `/api/projects/${project_id}/documents/${document_id}/extractions/${delete_extraction_id}`
  async function after_delete_extraction() {
    get_extractions()
  }

  let show_create_tag = false
  let tags_error: KilnError | null = null
  function add_tags(tags: string[]) {
    let prior_tags = document?.tags || []
    let new_tags = [...prior_tags, ...tags]
    let unique_tags = [...new Set(new_tags)]
    save_tags(unique_tags)
  }

  function remove_tag(tag: string) {
    let prior_tags = document?.tags || []
    let new_tags = prior_tags.filter((t) => t !== tag)
    save_tags(new_tags)
  }

  async function patch_document(patch_body: {
    name?: string
    description?: string
    tags?: string[]
  }) {
    const { data: document_response, error: patch_error } = await client.PATCH(
      "/api/projects/{project_id}/documents/{document_id}",
      {
        params: {
          path: {
            project_id,
            document_id,
          },
        },
        body: patch_body,
      },
    )
    if (patch_error) {
      throw patch_error
    }
    return document_response
  }

  async function save_tags(tags: string[]) {
    try {
      let patch_body = {
        tags: tags,
      }
      updated_document = await patch_document(patch_body)
      show_create_tag = false
      tags_error = null
    } catch (err) {
      tags_error = createKilnError(err)
    }
  }
</script>

<AppPage
  title="Document"
  subtitle={`${document?.name || document?.original_file.filename}`}
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/documents-and-search-rag#building-a-search-tool"
  limit_max_width
  breadcrumbs={[
    {
      label: "Docs & Search",
      href: `/docs/${project_id}`,
    },
    {
      label: "Document Library",
      href: `/docs/library/${project_id}`,
    },
  ]}
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
      handler: () => delete_document_dialog?.show(),
      shortcut: isMacOS() ? "Backspace" : "Delete",
    },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if document}
    <div class="flex flex-col xl:flex-row gap-8 xl:gap-16">
      {#if results}
        <div class="flex-grow">
          <div class="text-xl font-bold flex flex-row items-center gap-2">
            Document Extractions
            <InfoTooltip
              no_pad
              tooltip_text="Extractors generate a text representation of this document which can be indexed, searched and read by language models."
              position="bottom"
            />
          </div>
          {#if results.length == 0}
            <div class="mt-4 text-sm text-gray-500">
              No extractions found for this document.
            </div>
          {:else}
            <div class="text-sm overflow-x-auto rounded-lg border mt-4">
              <table class="table">
                <thead>
                  <tr>
                    <th>Extraction Details</th>
                    <th>Extraction Output</th>
                  </tr>
                </thead>
                <tbody>
                  {#each results as result}
                    <tr>
                      <td>
                        <div
                          class="grid grid-cols-[auto_1fr] gap-y-2 gap-x-4 text-sm"
                        >
                          <div>ID</div>
                          <div class="text-gray-500">{result.id}</div>
                          <div>Source</div>
                          <div class="text-gray-500">
                            {#if result.source == "processed"}
                              Model Output
                            {:else if result.source == "passthrough"}
                              Unprocessed (Original)
                            {:else}
                              {result.source}
                            {/if}
                          </div>
                          <div>Extractor</div>
                          <div class="text-gray-500">
                            <a
                              href={`/docs/extractors/${project_id}/${result.extractor.id}/extractor`}
                              class="link"
                            >
                              {result.extractor.name}
                            </a>
                          </div>
                          <div>Actions</div>
                          <div class="text-gray-500">
                            <button
                              class="link"
                              on:click={() => {
                                delete_extraction_id = result.id || null
                                delete_extraction_dialog?.show()
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      </td>
                      <td>
                        <button
                          class="text-left"
                          on:click={() => {
                            dialog_extraction = result
                            output_dialog?.show()
                          }}
                        >
                          <Output
                            raw_output={result.output_content}
                            max_height="200px"
                            hide_toggle={true}
                          />
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>
      {/if}

      <div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
        <PropertyList
          properties={[
            { name: "ID", value: document.id || "Unknown" },
            { name: "Name", value: document.name },
            {
              name: "Original Filename",
              value: document.original_file.filename,
            },
            {
              name: "Original File Size",
              value: formatSize(document.original_file.size),
            },
            {
              name: "Kind",
              value: capitalize(document.kind),
            },
            {
              name: "MIME Type",
              value: document.original_file.mime_type,
            },
            {
              name: "Created At",
              value: formatDate(document.created_at),
            },
            {
              name: "Created By",
              value: document.created_by || "Unknown",
            },
            {
              name: "Description",
              value: document.description || "None",
            },
          ]}
          title="Properties"
        />
        <div class="mt-8 mb-4">
          <div class="text-xl font-bold">Tags</div>
          <div class="flex flex-row flex-wrap gap-2 mt-2">
            {#each (document.tags || []).sort() as tag}
              <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
                <span class="truncate">{tag}</span>
                <button
                  class="pl-3 font-medium shrink-0"
                  on:click={() => remove_tag(tag)}>✕</button
                >
              </div>
            {/each}
            <button
              class="badge bg-gray-200 text-gray-500 p-3 font-medium {show_create_tag
                ? 'hidden'
                : ''}"
              on:click={() => (show_create_tag = true)}>+</button
            >
          </div>
          {#if show_create_tag}
            <div
              class="mt-3 flex flex-row gap-2 items-center {show_create_tag
                ? ''
                : 'hidden'}"
            >
              <TagDropdown
                on_select={(tag) => add_tags([tag])}
                on_escape={() => (show_create_tag = false)}
                focus_on_mount={true}
                example_tag_set="doc"
              />
              <div class="flex-none">
                <button
                  class="btn btn-sm btn-circle text-xl font-medium"
                  on:click={() => (show_create_tag = false)}>✕</button
                >
              </div>
            </div>
          {/if}
          {#if tags_error}
            <div class="text-error text-sm mt-2">
              {tags_error.getMessage() || "Error updating tags"}
            </div>
          {/if}
        </div>
      </div>
    </div>
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
  width="wide"
  action_buttons={[
    {
      label: "Close",
      isCancel: true,
    },
  ]}
>
  {#if dialog_extraction}
    <div class="mb-2 text-sm text-gray-500">
      The extractor produced the following output:
    </div>
    <Output raw_output={dialog_extraction.output_content} />
  {:else}
    <div class="text-sm text-gray-500">No extraction output found.</div>
  {/if}
</Dialog>

<DeleteDialog
  name={document?.name || "Document"}
  bind:this={delete_document_dialog}
  delete_url={delete_document_url}
  after_delete={after_document_delete}
/>

<DeleteDialog
  name="Extraction"
  bind:this={delete_extraction_dialog}
  delete_url={delete_extraction_url}
  after_delete={after_delete_extraction}
/>
