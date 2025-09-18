<script lang="ts">
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import { onMount } from "svelte"

  export let project_id: string
  export let selected_tags: string[] = []

  let available_tags: string[] = []
  let loading_tags = false
  let error: KilnError | null = null

  onMount(async () => {
    await loadAvailableTags()
  })

  async function loadAvailableTags() {
    loading_tags = true
    error = null

    try {
      const { data, error: load_available_tags_error } = await client.GET(
        "/api/projects/{project_id}/documents/tags",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (load_available_tags_error) {
        throw load_available_tags_error
      }

      available_tags = data || []
    } catch (e) {
      error = createKilnError(e as unknown)
      available_tags = []
    } finally {
      loading_tags = false
    }
  }

  function get_fancy_select_options(
    document_tags: string[],
    loading_tags: boolean,
  ) {
    if (loading_tags) {
      return [
        {
          label: "Loading document tags. Please wait...",
          options: [],
        },
      ]
    }
    if (document_tags.length === 0) {
      return [
        {
          label:
            "No documents have tags. Add tags in the document library to create a filter.",
          options: [],
        },
      ]
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
</script>

<div class="flex flex-col gap-4">
  {#if error}
    <div class="text-error text-sm">{error.message}</div>
  {:else}
    <FormElement
      id="tags_selector"
      label="Document Selection"
      description="Define which documents will be searched by this tool."
      info_description="If a tag filter is applied, only documents with those tags will be searched by this tool. You can add tags to your documents in the document library."
      inputType="multi_select"
      empty_label="All Documents in Library"
      fancy_select_options={get_fancy_select_options(
        available_tags,
        loading_tags,
      )}
      bind:value={selected_tags}
    />
  {/if}
</div>
