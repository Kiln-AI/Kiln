<script lang="ts">
  import { client } from "$lib/api_client"
  import FormElement from "$lib/utils/form_element.svelte"
  import { onMount } from "svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { load_document_tags } from "$lib/stores/document_tag_store"

  export let project_id: string
  export let selected_search_tool_id: string | null = null

  type SearchToolWithTags = {
    id: string
    tool_name: string
    name: string
    description: string | null
    tags: string[] | null
  }

  let search_tools_loading = false
  let search_tools: SearchToolWithTags[] = []

  function get_search_tool_options(tools: SearchToolWithTags[]): OptionGroup[] {
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
      search_tools = (data || []) as SearchToolWithTags[]
    } catch {
      // Error handling is done by the parent component
      search_tools = []
    } finally {
      search_tools_loading = false
    }
  }

  onMount(async () => {
    await load_search_tools()
  })
</script>

<FormElement
  id="search_tool_selector"
  label="Search Tool"
  description="Choose a Search Tool to evaluate."
  inputType="fancy_select"
  fancy_select_options={get_search_tool_options(search_tools)}
  bind:value={selected_search_tool_id}
  empty_state_message={search_tools_loading
    ? "Loading..."
    : search_tools.length === 0
      ? "No Search Tools"
      : undefined}
  empty_state_subtitle={search_tools_loading
    ? undefined
    : "Create a RAG Config to use it as a Search Tool."}
  empty_state_link={search_tools_loading
    ? undefined
    : `/settings/rag/${project_id}`}
/>
