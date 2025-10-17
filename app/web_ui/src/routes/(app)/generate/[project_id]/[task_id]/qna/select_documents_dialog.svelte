<script lang="ts">
  import { client } from "$lib/api_client"
  import type { DocumentLibraryState } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { createEventDispatcher, onMount } from "svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let dialog: Dialog | null = null
  export let keyboard_submit: boolean = false
  export let project_id: string
  export let available_tags: string[] = []
  const dispatch = createEventDispatcher()

  type SearchToolWithTags = {
    id: string
    tool_name: string
    name: string
    description: string | null
    tags: string[] | null
  }

  let selected_tags: string[] = []
  let submitting = false
  let library_state: DocumentLibraryState | null = null
  let library_state_loading = false
  let error: KilnError | null = null

  let search_tools_loading = false
  let search_tools: SearchToolWithTags[] = []
  let selected_search_tool_id: string | null = null
  let use_custom_tags = false

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

  function get_search_tool_options(tools: SearchToolWithTags[]): OptionGroup[] {
    console.info("get_search_tool_options", tools)
    if (!tools || tools.length === 0) {
      return []
    }
    return [
      {
        label: "Search Tools",
        options: tools.map((t) => ({
          value: t.id,
          label: t.name,
          description: t.description || undefined,
        })),
      },
    ]
  }

  async function select_documents_by_tag() {
    submitting = true
    error = null

    try {
      // If not using custom, derive tags from selected search tool
      if (!use_custom_tags) {
        const tool = search_tools.find((t) => t.id === selected_search_tool_id)
        selected_tags = tool?.tags ?? []
      }

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

  async function load_search_tools() {
    search_tools = []
    try {
      search_tools_loading = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/rag_configs",
        {
          params: {
            path: { project_id },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      console.info(data)
      search_tools = (data || []) as SearchToolWithTags[]
    } catch (e) {
      error = createKilnError(e as unknown)
      search_tools = []
    } finally {
      search_tools_loading = false
    }
  }

  onMount(async () => {
    await Promise.all([check_library_state(), load_search_tools()])
  })
</script>

<Dialog bind:this={dialog} title="Select a Search Tool" width="normal">
  {#if submitting || library_state_loading || search_tools_loading}
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
      submit_label="Select"
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
        id="search_tool_selector"
        label="Search Tool"
        description="Choose a Search Tool to evaluate."
        inputType="fancy_select"
        fancy_select_options={get_search_tool_options(search_tools)}
        bind:value={selected_search_tool_id}
        empty_state_message={search_tools.length === 0
          ? "No Search Tools"
          : undefined}
        empty_state_subtitle="Create a RAG Config to use it as a Search Tool."
        empty_state_link={`/settings/rag/${project_id}`}
      />

      {#if selected_search_tool_id}
        {#if !use_custom_tags}
          <div class="text-xs text-gray-500">
            {#if (search_tools.find((t) => t.id === selected_search_tool_id)?.tags ?? null) === null}
              <div class="mb-2">The following documents will be used:</div>
              <div class="badge badge-outline">All Documents</div>
            {:else}
              <div class="mb-2">
                The documents with the following tags will be used:
              </div>
              <div class="flex flex-wrap gap-2">
                {#each search_tools.find((t) => t.id === selected_search_tool_id)?.tags || [] as tag}
                  <div class="badge badge-outline">{tag}</div>
                {/each}
              </div>
            {/if}
            <div class="mt-3">
              <button
                type="button"
                class="btn btn-sm px-6"
                on:click={() => {
                  use_custom_tags = true
                  const tool = search_tools.find(
                    (t) => t.id === selected_search_tool_id,
                  )
                  selected_tags = tool?.tags ? [...tool.tags] : []
                }}>Use Custom Tags</button
              >
            </div>
          </div>
        {:else}
          <FormElement
            id="custom_tags_selector_modal"
            label="Custom Tags"
            description="Override the Search Tool tags. Leave empty to use all documents."
            info_description="If a tag filter is applied, only documents with those tags will be used during Q&A generation. You can add tags to your documents in the document library."
            inputType="multi_select"
            empty_label="All Documents in Library"
            fancy_select_options={get_fancy_select_options_tags(available_tags)}
            bind:value={selected_tags}
            empty_state_message="No Document Tags"
            empty_state_subtitle="Add tags to documents in the document library to filter documents."
            empty_state_link={`/docs/library/${project_id}`}
          />
          <div class="mt-2">
            <button
              type="button"
              class="btn btn-sm px-6"
              on:click={() => {
                use_custom_tags = false
              }}>Use Same Tags as Search Tool</button
            >
          </div>
        {/if}
      {/if}
    </FormContainer>
  {/if}
</Dialog>
