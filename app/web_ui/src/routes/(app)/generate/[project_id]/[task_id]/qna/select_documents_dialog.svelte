<script lang="ts">
  import { client } from "$lib/api_client"
  import Dialog from "$lib/ui/dialog.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createEventDispatcher } from "svelte"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
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
      dialog?.close()

      // Reset state
      selected_tags = []
    } catch (e) {
      error = createKilnError(e as unknown)
    } finally {
      loading = false
    }
  }
</script>

<Dialog bind:this={dialog} title="Select Documents" width="normal">
  <FormContainer
    submit_visible={true}
    submit_label="Add Documents"
    on:submit={async (_) => {
      await add_documents()
    }}
    {error}
    gap={4}
    bind:submitting={loading}
    {keyboard_submit}
    on:close={() => dispatch("close")}
  >
    {#if loading}
      <div class="flex flex-row justify-center">
        <div class="loading loading-spinner loading-lg my-12"></div>
      </div>
    {:else}
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
    {/if}
  </FormContainer>
</Dialog>
