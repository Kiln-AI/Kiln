<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import type { KilnDocument } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { load_model_info } from "$lib/stores"
  import { page } from "$app/stores"
  import { goto, replaceState } from "$app/navigation"
  import Dialog from "$lib/ui/dialog.svelte"
  import EmptyDocsLibraryIntro from "./empty_docs_library_intro.svelte"
  import FileIcon from "../../fileicon.svelte"
  import {
    formatDate,
    formatSize,
    mime_type_to_string,
  } from "$lib/utils/formatters"
  import UploadFileDialog from "./upload_file_dialog.svelte"

  import { ragProgressStore } from "$lib/stores/rag_progress_store"
  import TagDropdown from "$lib/ui/tag_dropdown.svelte"

  let upload_file_dialog: UploadFileDialog | null = null

  let documents: KilnDocument[] | null = null
  let filtered_documents: KilnDocument[] | null = null
  let error: KilnError | null = null
  let loading = true
  let sortColumn = ($page.url.searchParams.get("sort") || "created_at") as
    | keyof KilnDocument
    | "name"
    | "kind"
    | "created_at"
    | "original_file.size"
  let sortDirection = ($page.url.searchParams.get("order") || "desc") as
    | "asc"
    | "desc"
  let filter_tags = ($page.url.searchParams.getAll("tags") || []) as string[]
  let page_number: number = parseInt(
    $page.url.searchParams.get("page") || "1",
    10,
  )
  const page_size = 1000
  $: {
    // Update based on live URL
    const url = new URL(window.location.href)
    sortColumn = (url.searchParams.get("sort") ||
      "created_at") as typeof sortColumn
    sortDirection = (url.searchParams.get("order") ||
      "desc") as typeof sortDirection
    filter_tags = url.searchParams.getAll("tags") as string[]
    page_number = parseInt(url.searchParams.get("page") || "1", 10)
    sortDocuments()
  }

  $: project_id = $page.params.project_id

  const columns = [
    { key: "kind", label: "Type" },
    { key: "name", label: "Name" },
    { key: "original_file.size", label: "Size" },
    { key: "created_at", label: "Created At" },
  ]

  onMount(async () => {
    get_documents()
  })

  async function get_documents() {
    try {
      load_model_info()
      loading = true
      if (!project_id) {
        throw new Error("Project ID not set.")
      }
      const { data: documents_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/documents",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      documents = documents_response
      sortDocuments()
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

  function sortFunction(a: KilnDocument, b: KilnDocument) {
    let aValue: string | number | Date | null | undefined
    let bValue: string | number | Date | null | undefined

    switch (sortColumn) {
      case "id":
        aValue = a.id
        bValue = b.id
        break
      case "created_at":
        aValue = a.created_at
        bValue = b.created_at
        break
      case "name":
        aValue = a.name
        bValue = b.name
        break
      case "kind":
        aValue = a.kind + a.original_file.mime_type
        bValue = b.kind + b.original_file.mime_type
        break
      case "original_file.size":
        aValue = a.original_file.size
        bValue = b.original_file.size
        break
      default:
        return 0
    }

    if (!aValue) return sortDirection === "asc" ? 1 : -1
    if (!bValue) return sortDirection === "asc" ? -1 : 1

    if (aValue < bValue) return sortDirection === "asc" ? -1 : 1
    if (aValue > bValue) return sortDirection === "asc" ? 1 : -1
    return 0
  }

  function handleSort(columnString: string) {
    const new_column = columnString as typeof sortColumn
    let new_direction = "desc"
    if (sortColumn === new_column) {
      new_direction = sortDirection === "asc" ? "desc" : "asc"
    } else {
      new_direction = "desc"
    }
    updateURL({
      sort: new_column,
      order: new_direction,
    })
  }

  function sortDocuments() {
    if (!documents) return
    documents = documents ? [...documents].sort(sortFunction) : null
    filtered_documents = documents
      ? [...documents].filter((document) =>
          filter_tags.every((tag) => document.tags?.includes(tag)),
        )
      : null

    // Clear the last selected id, as it's moved
    last_selected_id = null
  }

  let filter_tags_dialog: Dialog | null = null

  function remove_filter_tag(tag: string) {
    const newTags = filter_tags.filter((t) => t !== tag)
    updateURL({
      tags: newTags,
      page: 1,
    })
  }

  function add_filter_tag(tag: string) {
    const newTags = [...new Set([...filter_tags, tag])]
    // Selections confusing as filters change
    select_mode = false
    selected_documents = new Set()
    updateURL({
      tags: newTags,
      page: 1,
    })
  }

  $: available_filter_tags = get_available_filter_tags(
    filtered_documents,
    filter_tags,
  )
  function get_available_filter_tags(
    filtered_documents: KilnDocument[] | null,
    filter_tags: string[],
  ): Record<string, number> {
    if (!filtered_documents) return {}

    const remaining_tags: Record<string, number> = {}
    filtered_documents.forEach((document) => {
      document.tags?.forEach((tag) => {
        if (filter_tags.includes(tag)) return
        if (typeof tag === "string") {
          remaining_tags[tag] = (remaining_tags[tag] || 0) + 1
        }
      })
    })
    return remaining_tags
  }

  function updateURL(params: Record<string, string | string[] | number>) {
    // update the URL so you can share links
    const url = new URL(window.location.href)

    // we're using multiple tags, so we need to delete the existing tags
    if (params.tags) {
      url.searchParams.delete("tags")
    }

    // Add new params to the URL (keep current params)
    Object.entries(params).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, v))
      } else {
        url.searchParams.set(key, value.toString())
      }
    })

    // Update state manually
    if (params.sort) {
      sortColumn = params.sort as typeof sortColumn
    }
    if (params.order) {
      sortDirection = params.order as typeof sortDirection
    }
    if (params.tags) {
      filter_tags = params.tags as string[]
    }
    if (params.page) {
      page_number = params.page as number
    }

    // Use replaceState to avoid adding new entries to history
    replaceState(url, {})

    sortDocuments()
  }

  let select_mode: boolean = false
  let selected_documents: Set<string> = new Set()
  let select_document: "all" | "none" | "some" = "none"
  $: {
    if (selected_documents.size >= (filtered_documents?.length || 0)) {
      select_document = "all"
    } else if (selected_documents.size > 0) {
      select_document = "some"
    } else {
      select_document = "none"
    }
  }

  function toggle_selection(document_id: string): boolean {
    const was_selected = selected_documents.has(document_id)
    if (was_selected) {
      selected_documents.delete(document_id)
    } else {
      selected_documents.add(document_id)
    }
    // Reactivity trigger
    selected_documents = selected_documents

    return !was_selected
  }

  let last_selected_id: string | null = null
  function row_clicked(document_id: string | null, event: MouseEvent) {
    if (!document_id) {
      last_selected_id = null
      return
    }
    if (select_mode) {
      const selected = toggle_selection(document_id)

      // Potentially select a range of documents if SHIFT-click
      if (selected) {
        select_range(document_id, event)
      }
      last_selected_id = selected ? document_id : null
    } else {
      open_document(document_id)
    }
  }

  function open_document(document_id: string) {
    const url = `/docs/library/${project_id}/${document_id}`
    goto(url)
  }

  // Select a range of documents if SHIFT-click
  function select_range(document_id: string, event: MouseEvent) {
    if (!last_selected_id) return
    // return unless shift key is down
    if (!event.shiftKey) return

    // select all documents between last_selected_id and document_id
    const last_selected_index = documents?.findIndex(
      (document) => document.id === last_selected_id,
    )
    const document_index = documents?.findIndex(
      (document) => document.id === document_id,
    )
    if (
      last_selected_index === -1 ||
      document_index === -1 ||
      last_selected_index === undefined ||
      document_index === undefined
    )
      return
    const start_index = Math.min(last_selected_index, document_index)
    const end_index = Math.max(last_selected_index, document_index)
    for (let i = start_index; i <= end_index; i++) {
      const id = documents?.[i]?.id
      if (id) {
        selected_documents.add(id)
      }
    }
    // Reactivity trigger
    selected_documents = selected_documents
  }

  function select_all_clicked(event: Event) {
    // Prevent default checkbox, we're using reactivity
    event.preventDefault()

    // Clear the last selected id, it no longer makes sense
    last_selected_id = null

    if (select_document === "all" || select_document === "some") {
      selected_documents.clear()
    } else {
      filtered_documents?.forEach((document) => {
        if (document.id) {
          selected_documents.add(document.id)
        }
      })
    }
    selected_documents = selected_documents
  }

  let delete_dialog: Dialog | null = null

  function show_delete_modal() {
    delete_dialog?.show()
  }

  async function delete_documents(): Promise<boolean> {
    try {
      const { error } = await client.POST(
        "/api/projects/{project_id}/documents/delete",
        {
          params: {
            path: { project_id },
          },
          body: Array.from(selected_documents),
        },
      )
      if (error) {
        throw error
      }

      // Close modal on success
      return true
    } catch (e) {
      throw createKilnError(e)
    } finally {
      // Reload UI, even on failure, as partial delete is possible
      selected_documents = new Set()
      select_mode = false
      await get_documents()
    }
  }

  let add_tags: Set<string> = new Set()
  let remove_tags: Set<string> = new Set()
  let show_add_tag_dropdown = false
  let current_tag: string = ""

  let add_tags_dialog: Dialog | null = null

  function show_add_tags_modal() {
    // Show the dropdown
    show_add_tag_dropdown = true

    add_tags_dialog?.show()
  }

  async function add_selected_tags(): Promise<boolean> {
    // Special case for this UI - consider the partly filled tag in the input
    // as a tag to add
    if (current_tag.length > 0) {
      add_tags.add(current_tag)
      current_tag = ""
    }
    // Don't accidentially remove tags
    remove_tags = new Set()
    return await edit_tags()
  }

  let removeable_tags: Record<string, number> = {}
  function update_removeable_tags() {
    let select_document_contents: KilnDocument[] = []
    for (const document of filtered_documents || []) {
      if (document.id && selected_documents.has(document.id)) {
        select_document_contents.push(document)
      }
    }
    removeable_tags = get_available_filter_tags(
      select_document_contents,
      Array.from(remove_tags),
    )
  }

  let remove_tags_dialog: Dialog | null = null

  function show_remove_tags_modal() {
    // clear prior lists
    remove_tags = new Set()

    update_removeable_tags()

    remove_tags_dialog?.show()
  }

  async function remove_selected_tags(): Promise<boolean> {
    // Don't accidentially add tags
    add_tags = new Set()
    return await edit_tags()
  }

  async function edit_tags(): Promise<boolean> {
    try {
      const { error } = await client.POST(
        "/api/projects/{project_id}/documents/edit_tags",
        {
          params: { path: { project_id } },
          body: {
            document_ids: Array.from(selected_documents),
            add_tags: Array.from(add_tags),
            remove_tags: Array.from(remove_tags),
          },
        },
      )
      if (error) {
        throw error
      }

      // Hide the dropdown (safari bug shows it when hidden)
      show_add_tag_dropdown = false

      // trigger all rag configs to re-run because tagging documents may
      // have changed which documents are targeted by which rag configs
      ragProgressStore.run_all_rag_configs(project_id).catch((error) => {
        console.error("Error running all rag configs", error)
      })

      // Close modal on success
      return true
    } finally {
      // Reload UI, even on failure, as partial delete is possible
      selected_documents = new Set()
      select_mode = false
      await get_documents()
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Document Library"
    subtitle="Add or Browse Documents"
    no_y_padding
    breadcrumbs={[{ label: "Docs & Search", href: `/docs/${project_id}` }]}
    action_buttons={documents && documents.length == 0
      ? []
      : [
          {
            label: "Add Documents",
            handler: () => {
              upload_file_dialog?.show()
            },
            primary: true,
          },
        ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if documents && documents.length == 0}
      <div class="flex flex-col items-center justify-center min-h-[75vh]">
        <EmptyDocsLibraryIntro action={() => upload_file_dialog?.show()} />
      </div>
    {:else if documents}
      <div class="mb-4">
        <div
          class="flex flex-row items-center justify-end py-2 gap-3 {select_mode
            ? 'sticky top-0 z-10 backdrop-blur'
            : ''}"
        >
          {#if select_mode}
            <div class="font-light text-sm">
              {selected_documents.size} selected
            </div>
            {#if selected_documents.size > 0}
              <div class="dropdown dropdown-end">
                <div tabindex="0" role="button" class="btn btn-mid !px-3">
                  <img alt="tags" src="/images/tag.svg" class="w-5 h-5" />
                </div>
                <ul
                  class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
                >
                  <li>
                    <button tabindex="0" on:click={() => show_add_tags_modal()}>
                      Add Tags
                    </button>
                  </li>
                  <li>
                    <button
                      tabindex="0"
                      on:click={() => show_remove_tags_modal()}
                    >
                      Remove Tags
                    </button>
                  </li>
                </ul>
              </div>
              <button
                class="btn btn-mid !px-3"
                on:click={() => show_delete_modal()}
              >
                <img alt="delete" src="/images/delete.svg" class="w-5 h-5" />
              </button>
            {/if}
            <button class="btn btn-mid" on:click={() => (select_mode = false)}>
              Cancel Selection
            </button>
          {:else}
            <button class="btn btn-mid" on:click={() => (select_mode = true)}>
              Select
            </button>
            <button
              class="btn btn-mid !px-3"
              on:click={() => filter_tags_dialog?.show()}
            >
              <img alt="filter" src="/images/filter.svg" class="w-5 h-5" />
              {#if filter_tags.length > 0}
                <span class="badge badge-primary badge-sm"
                  >{filter_tags.length}</span
                >
              {/if}
            </button>
          {/if}
        </div>
        <div class="overflow-x-auto rounded-lg border">
          <table class="table">
            <thead>
              <tr>
                {#if select_mode}
                  <th>
                    {#key select_document}
                      <input
                        type="checkbox"
                        class="checkbox checkbox-sm mt-1"
                        checked={select_document === "all"}
                        indeterminate={select_document === "some"}
                        on:change={(e) => select_all_clicked(e)}
                      />
                    {/key}
                  </th>
                {/if}
                {#each columns as { key, label }}
                  <th
                    on:click={() => handleSort(key)}
                    class="hover:bg-base-200 cursor-pointer"
                  >
                    {label}
                    {sortColumn === key
                      ? sortDirection === "asc"
                        ? "▲"
                        : "▼"
                      : ""}
                  </th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each (filtered_documents || []).slice((page_number - 1) * page_size, page_number * page_size) as document}
                <tr
                  class="{select_mode
                    ? ''
                    : 'hover'} cursor-pointer {select_mode &&
                  document.id &&
                  selected_documents.has(document.id)
                    ? 'bg-base-200'
                    : ''}"
                  on:click={(event) => {
                    row_clicked(document.id || null, event)
                  }}
                >
                  {#if select_mode}
                    <td class="w-12">
                      <input
                        type="checkbox"
                        class="checkbox checkbox-sm"
                        checked={(document.id &&
                          selected_documents.has(document.id)) ||
                          false}
                      />
                    </td>
                  {/if}
                  <td>
                    <div class="flex flex-row items-center gap-2">
                      <FileIcon kind={document.kind} />
                      <span class="text-sm">
                        {mime_type_to_string(document.original_file.mime_type)}
                      </span>
                    </div>
                  </td>
                  <td>{document.name}</td>
                  <td>{formatSize(document.original_file.size)}</td>
                  <td>{formatDate(document.created_at)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      {#if page_number > 1 || (filtered_documents && filtered_documents.length > page_size)}
        <div class="flex flex-row justify-center mt-10">
          <div class="join">
            {#each Array.from({ length: Math.ceil(documents.length / page_size) }, (_, i) => i + 1) as page}
              <button
                class="join-item btn {page_number == page ? 'btn-active' : ''}"
                on:click={() => updateURL({ page: page })}
              >
                {page}
              </button>
            {/each}
          </div>
        </div>
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
</div>

<Dialog
  bind:this={filter_tags_dialog}
  title="Filter Documents by Tags"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  {#if filter_tags.length > 0}
    <div class="text-sm mb-2 font-medium">Current Filters:</div>
  {/if}
  <div class="flex flex-row gap-2 flex-wrap">
    {#each filter_tags as tag}
      <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
        <span class="truncate">{tag}</span>
        <button
          class="pl-3 font-medium shrink-0"
          on:click={() => remove_filter_tag(tag)}>✕</button
        >
      </div>
    {/each}
  </div>

  <div class="text-sm mt-4 mb-2 font-medium">Add a filter:</div>
  {#if Object.keys(available_filter_tags).length == 0}
    <p class="text-sm text-gray-500">
      Any further filters would show zero results.
    </p>
  {/if}
  <div class="flex flex-row gap-2 flex-wrap">
    {#each Object.entries(available_filter_tags).sort((a, b) => b[1] - a[1]) as [tag, count]}
      <button
        class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full"
        on:click={() => add_filter_tag(tag)}>{tag} ({count})</button
      >
    {/each}
  </div>
</Dialog>

<Dialog
  bind:this={delete_dialog}
  title={selected_documents.size > 1
    ? "Delete " + selected_documents.size + " Documents"
    : "Delete Document"}
  action_buttons={[
    { label: "Cancel", isCancel: true },
    { label: "Delete", asyncAction: () => delete_documents(), isError: true },
  ]}
>
  <div class="text-sm font-light text-gray-500">This cannot be undone.</div>
</Dialog>

<Dialog
  bind:this={add_tags_dialog}
  title={selected_documents.size > 1
    ? "Add Tags to " + selected_documents.size + " Documents"
    : "Add Tags to Document"}
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Add Tags",
      asyncAction: add_selected_tags,
      disabled: add_tags.size == 0 && !current_tag,
      isPrimary: true,
    },
  ]}
>
  <div>
    <div class="text-sm font-light text-gray-500 mb-2">
      Tags can be used to organize you documents.
    </div>
    <div class="flex flex-row flex-wrap gap-2 mt-2">
      {#each Array.from(add_tags).sort() as tag}
        <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
          <span class="truncate">{tag}</span>
          <button
            class="pl-3 font-medium shrink-0"
            on:click={() => {
              add_tags.delete(tag)
              add_tags = add_tags
            }}>✕</button
          >
        </div>
      {/each}
      <button
        class="badge bg-gray-200 text-gray-500 p-3 font-medium {show_add_tag_dropdown
          ? 'hidden'
          : ''}"
        on:click={() => (show_add_tag_dropdown = true)}>+</button
      >
    </div>
    {#if show_add_tag_dropdown}
      <div
        class="mt-3 flex flex-row gap-2 items-center {show_add_tag_dropdown
          ? ''
          : 'hidden'}"
      >
        <TagDropdown
          bind:tag={current_tag}
          on_select={(tag) => {
            add_tags.add(tag)
            add_tags = add_tags
            show_add_tag_dropdown = false
            current_tag = ""
          }}
          on_escape={() => (show_add_tag_dropdown = false)}
          example_tag_set="doc"
          focus_on_mount={true}
        />
        <div class="flex-none">
          <button
            class="btn btn-sm btn-circle text-xl font-medium"
            on:click={() => (show_add_tag_dropdown = false)}>✕</button
          >
        </div>
      </div>
    {/if}
  </div>
</Dialog>

<Dialog
  bind:this={remove_tags_dialog}
  title={selected_documents.size > 1
    ? "Remove Tags from " + selected_documents.size + " Documents"
    : "Remove Tags from Document"}
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Remove Tags",
      asyncAction: () => remove_selected_tags(),
      disabled: remove_tags.size == 0,
      isError: true,
    },
  ]}
>
  <div>
    <div class="text-sm font-light text-gray-500 mt-6">
      Selected tags to remove:
    </div>
    {#if remove_tags.size == 0}
      <div class="text-xs font-medium">No tags selected.</div>
    {:else}
      <div class="flex flex-row flex-wrap gap-2 mt-2">
        {#each Array.from(remove_tags).sort() as tag}
          <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
            <span class="truncate">{tag}</span>
            <button
              class="pl-3 font-medium shrink-0"
              on:click={() => {
                remove_tags.delete(tag)
                remove_tags = remove_tags
                update_removeable_tags()
              }}>✕</button
            >
          </div>
        {/each}
      </div>
    {/if}
    <div class="text-sm font-light text-gray-500 mt-6">Available tags:</div>
    {#if Object.keys(removeable_tags).length == 0 && remove_tags.size == 0}
      <div class="text-xs font-medium">No tags on selected documents.</div>
    {:else if Object.keys(removeable_tags).length == 0}
      <div class="text-xs font-medium">
        All available tags already selected.
      </div>
    {:else}
      <div class="flex flex-row flex-wrap gap-2 mt-2">
        {#each Object.entries(removeable_tags).sort((a, b) => b[1] - a[1]) as [tag, count]}
          {#if !remove_tags.has(tag)}
            <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
              <button
                class="truncate"
                on:click={() => {
                  remove_tags.add(tag)
                  remove_tags = remove_tags
                  update_removeable_tags()
                }}
              >
                {tag} ({count})
              </button>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  </div>
</Dialog>

<UploadFileDialog
  bind:this={upload_file_dialog}
  onUploadCompleted={() => {
    get_documents()
  }}
/>
