<script lang="ts">
  import { client } from "$lib/api_client"
  import Dialog from "$lib/ui/dialog.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createEventDispatcher } from "svelte"
  import type { DocumentLibraryState, KilnDocument } from "$lib/types"
  import FormElement from "$lib/utils/form_element.svelte"
  import { onMount } from "svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import {
    document_tag_store_by_project_id,
    load_document_tags,
  } from "$lib/stores/document_tag_store"
  import { derived } from "svelte/store"

  $: available_tags = derived(document_tag_store_by_project_id, ($store) => {
    const tag_counts = $store[project_id]
    return tag_counts ? Object.keys(tag_counts) : []
  })

  onMount(async () => {
    await Promise.all([check_library_state(), load_document_tags(project_id)])
  })

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let project_id: string

  const dispatch = createEventDispatcher<{
    documents_added: {
      documents: KilnDocument[]
      tags: string[]
    }
    close: void
  }>()

  let selected_tags: string[] = []
  let error: KilnError | null = null
  let library_state: DocumentLibraryState | null = null
  let library_state_loading = false

  function get_fancy_select_options_tags(tags: string[]): OptionGroup[] {
    if (tags.length === 0) {
      return []
    }
    return [
      {
        label: "Document Tags",
        options: tags.map((tag) => ({
          label: tag,
          value: tag,
        })),
      },
    ]
  }

  onMount(async () => {
    await load_document_tags(project_id)
  })

  async function fetch_documents_by_tag() {
    error = null

    try {
      // Fetch documents based on selected tags
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/documents",
        {
          params: {
            path: {
              project_id,
            },
            query: {
              tags: selected_tags.join(","),
            },
          },
        },
      )

      if (fetch_error) {
        throw fetch_error
      }

      const documents = data || []

      // Dispatch event with selected documents
      dispatch("documents_added", { documents, tags: selected_tags })

      // Close modal
      dialog?.close()

      // Reset state
      selected_tags = []
    } catch (e) {
      error = createKilnError(e as unknown)
    }
  }

  async function check_library_state() {
    library_state = null
    try {
      library_state_loading = true
      error = null
      const { data, error: check_error } = await client.GET(
        "/api/projects/{project_id}/check_library_state",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (check_error) {
        throw check_error
      }

      library_state = data
    } catch (e) {
      error = createKilnError(e as unknown)
    } finally {
      library_state_loading = false
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title="Select Documents"
  subtitle="Choose documents for Q&A generation."
  width="normal"
>
  <FormContainer
    submit_visible={!library_state_loading && !library_state?.is_empty}
    submit_label="Select Documents"
    on:submit={async (_) => {
      await fetch_documents_by_tag()
    }}
    {error}
    gap={4}
    {keyboard_submit}
    on:close={() => dispatch("close")}
  >
    {#if library_state_loading}
      <div class="flex flex-row justify-center">
        <div class="loading loading-spinner loading-lg my-12"></div>
      </div>
    {:else if library_state?.is_empty}
      <div class="flex flex-row gap-3">
        <div class="text-xs text-gray-500 text-start">
          <span>Looks like you don't have any documents yet.</span>
          <a href={`/docs/library/${project_id}`} class="link">
            Create documents
          </a> to get started.
        </div>
      </div>
    {:else}
      <FormElement
        id="custom_tags_selector_modal"
        label="Documents"
        description="Use all documents in the library, or filter by specific tags."
        info_description="If a tag filter is applied, only documents with those tags will be used during Q&A generation. You can add tags to your documents in the document library."
        inputType="multi_select"
        empty_label="All Documents in Library"
        fancy_select_options={get_fancy_select_options_tags($available_tags)}
        bind:value={selected_tags}
        empty_state_message="No Document Tags"
        empty_state_subtitle="Add tags to documents in the document library to filter documents."
        empty_state_link={`/docs/library/${project_id}`}
      />
    {/if}
  </FormContainer>
</Dialog>
