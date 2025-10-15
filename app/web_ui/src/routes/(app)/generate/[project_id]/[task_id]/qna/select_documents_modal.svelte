<script lang="ts">
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createEventDispatcher } from "svelte"

  export let id: string
  export let project_id: string
  export let available_tags: string[] = []

  const dispatch = createEventDispatcher()

  let selected_tags: string[] = []
  let loading = false
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

  async function add_documents() {
    loading = true
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
      const modal = document.getElementById(id)
      // @ts-expect-error dialog is not a standard element
      modal?.close()

      // Reset state
      selected_tags = []
    } catch (e) {
      error = createKilnError(e as unknown)
    } finally {
      loading = false
    }
  }
</script>

<dialog {id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold">Select Documents</h3>
    <p class="text-sm font-light mb-8">
      Choose which documents to generate Q&A pairs from.
    </p>

    {#if loading}
      <div class="flex flex-row justify-center">
        <div class="loading loading-spinner loading-lg my-12"></div>
      </div>
    {:else}
      <div class="flex flex-col gap-6">
        <FormElement
          id="tags_selector_modal"
          label="Document Selection"
          description="Choose which documents to generate Q&A pairs from."
          info_description="If tag filters are applied, only documents with those tags will be used. Leave empty to use all documents."
          inputType="multi_select"
          empty_label="All Documents in Library"
          fancy_select_options={get_fancy_select_options_tags(available_tags)}
          bind:value={selected_tags}
          empty_state_message="No documents have tags."
          empty_state_subtitle="Add tags in the document library to create filters."
          empty_state_link={`/docs/library/${project_id}`}
        />

        {#if error}
          <div class="text-error text-sm mt-4">
            {error.getMessage()}
          </div>
        {/if}

        <button class="btn btn-primary mt-6" on:click={add_documents}>
          Add Documents
        </button>
      </div>
    {/if}
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
