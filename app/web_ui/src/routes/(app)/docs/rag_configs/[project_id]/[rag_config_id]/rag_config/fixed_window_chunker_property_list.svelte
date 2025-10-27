<script lang="ts">
  import PropertyList from "$lib/ui/property_list.svelte"
  import { chunker_type_format } from "$lib/utils/formatters"

  export let chunk_size: number
  export let chunk_overlap: number

  const friendly_chunker_type = chunker_type_format("fixed_window")
  const strategy_tooltip = `The ${friendly_chunker_type} chunking algorithm splits the text into fixed-size chunks of a specified number of words, while respecting sentence boundaries.`
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
      name: "Chunk Size",
      value: chunk_size ? `${String(chunk_size)} words` : "N/A",
      tooltip: "The approximate number of words to include in each chunk",
    },
    {
      name: "Overlap",
      value: chunk_overlap ? `${String(chunk_overlap)} words` : "N/A",
      tooltip: "The approximate number of words to overlap between chunks",
    },
  ]}
/>
