<script lang="ts">
  import { client } from "$lib/api_client"
  import { embedding_model_name } from "$lib/stores"
  import type { EmbeddingConfig } from "$lib/types"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { chunker_type_format } from "$lib/utils/formatters"
  import { onMount } from "svelte"

  export let project_id: string
  export let buffer_size: number
  export let breakpoint_percentile_threshold: number
  export let embedding_config_id: string

  const friendly_chunker_type = chunker_type_format("semantic")
  const strategy_tooltip = `The ${friendly_chunker_type} chunking algorithm splits the text into semantically related chunks using semantic similarity to group sentences together.`

  let loading_embedding_config: boolean = false
  let embedding_config: EmbeddingConfig | null = null
  let error: KilnError | null = null

  onMount(async () => {
    await get_embedding_config()
  })

  async function get_embedding_config() {
    try {
      loading_embedding_config = true
      const { error: get_embedding_config_error, data: embedding_config_data } =
        await client.GET(
          "/api/projects/{project_id}/embedding_configs/{embedding_config_id}",
          {
            params: { path: { project_id, embedding_config_id } },
          },
        )
      if (get_embedding_config_error) {
        throw get_embedding_config_error
      }
      embedding_config = embedding_config_data
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading_embedding_config = false
    }
  }

  function format_percentile(percentile: number) {
    return `${String(percentile)}%`
  }

  function format_buffer_size(buffer_size: number) {
    return `${String(buffer_size)} sentences`
  }
</script>

<PropertyList
  title="Chunker"
  properties={[
    {
      name: "Strategy",
      value: friendly_chunker_type || "Unknown",
      tooltip: strategy_tooltip,
    },
    {
      name: "Buffer Size",
      value: buffer_size ?? null ? format_buffer_size(buffer_size) : "N/A",
      tooltip:
        "The number of sentences to group together when evaluating semantic similarity.",
    },
    {
      name: "Breakpoint Percentile",
      value:
        breakpoint_percentile_threshold ?? null
          ? format_percentile(breakpoint_percentile_threshold)
          : "N/A",
      tooltip:
        "The percentile of cosine dissimilarity that must be exceeded between a group of sentences and the next to create a breakpoint.",
    },
    {
      name: "Embedding Model",
      value: loading_embedding_config
        ? "Loading..."
        : error
          ? error.getMessage()
          : embedding_config
            ? `${embedding_model_name(embedding_config.model_name, embedding_config.model_provider_name)}`
            : "N/A",
      tooltip: "The embedding model used to create semantic vectors.",
    },
  ]}
/>
