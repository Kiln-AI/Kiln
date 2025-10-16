<script lang="ts">
  import { client } from "$lib/api_client"
  import type { DocumentLibraryState } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createEventDispatcher, onMount } from "svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let project_id: string
  export let available_tags: string[] = []
  const dispatch = createEventDispatcher()

  let selected_tags: string[] = []
  let submitting = false
  let library_state: DocumentLibraryState | null = null
  let library_state_loading = false
  let error: KilnError | null = null

  function get_fancy_select_options_tags(document_tags: string[]) {
    if (document_tags.length === 0) {
      return []
    }
    return [
      {
        label: "Filter by Document Tag",
        options: document_tags.map((tag) => ({
          label: tag,
          value: tag,
        })),
      },
    ]
  }

  async function select_documents_by_tag() {
    submitting = true
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
    } finally {
      submitting = false
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

  onMount(async () => {
    await check_library_state()
  })
</script>

<Dialog bind:this={dialog} title="Select Documents" width="normal">
  {#if submitting || library_state_loading}
    <div class="flex flex-row justify-center">
      <div class="loading loading-spinner loading-lg my-12"></div>
    </div>
  {:else if library_state?.is_empty}
    <div class="text-xs text-gray-500 text-start">
      <p>Looks like you don't have any documents yet.</p>
      <p>
        <a href={`/docs/library/${project_id}`} class="link">
          Create documents
        </a>
        to get started.
      </p>
    </div>
  {:else}
    <FormContainer
      submit_visible={true}
      submit_label="Select Documents"
      on:submit={async (_) => {
        await select_documents_by_tag()
      }}
      {error}
      gap={4}
      bind:submitting
      {keyboard_submit}
      on:close={() => dispatch("close")}
    >
      <FormElement
        id="tags_selector_modal"
        label="Document Selection"
        description="Choose which documents to generate Q&A pairs from."
        info_description="If tag filters are applied, only documents with those tags will be used. Leave empty to use all documents."
        inputType="multi_select"
        empty_label="All Documents in Library"
        fancy_select_options={get_fancy_select_options_tags(available_tags)}
        bind:value={selected_tags}
        empty_state_message="No Document Tags"
        empty_state_subtitle="Add tags to documents in the document library to filter documents."
        empty_state_link={`/docs/library/${project_id}`}
      />
    </FormContainer>
  {/if}
</Dialog>
