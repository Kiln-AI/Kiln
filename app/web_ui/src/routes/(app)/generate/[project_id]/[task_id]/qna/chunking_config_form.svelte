<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { number_validator } from "$lib/utils/input_validators"

  export let split_documents_into_chunks: boolean = false
  export let chunk_size_tokens: number | null = null
  export let chunk_overlap_tokens: number | null = null

  $: {
    if (!split_documents_into_chunks) {
      chunk_size_tokens = null
      chunk_overlap_tokens = null
    } else if (chunk_size_tokens === null && chunk_overlap_tokens === null) {
      chunk_size_tokens = 8192
      chunk_overlap_tokens = 256
    }
  }
</script>

<div class="space-y-4">
  <FormElement
    id="split_documents_into_chunks_checkbox"
    inputType="checkbox"
    label="Split documents into smaller chunks"
    description="Useful for very long documents"
    info_description="For very long documents such as books, manuals, or transcripts, splitting into smaller chunks helps create more focused content."
    bind:value={split_documents_into_chunks}
  />

  {#if split_documents_into_chunks}
    <div class="pl-6 space-y-3 border-l-2 border-base-300 ml-10">
      <FormElement
        id="chunk_size_tokens"
        inputType="input_number"
        label="Chunk size (tokens)"
        description="Approximate number of tokens per chunk"
        info_description="Smaller chunks allow for more granular processing, but may not encapsulate broader context."
        bind:value={chunk_size_tokens}
        validator={(value) =>
          number_validator({
            min: 1,
            integer: true,
            label: "Chunk Size",
            optional: false,
          })(value)}
      />
      <FormElement
        id="chunk_overlap_tokens"
        inputType="input_number"
        label="Chunk overlap (tokens)"
        description="Number of tokens to overlap between chunks"
        info_description="Overlap ensures sentences that span boundaries aren't lost because they're fully contained in at least one chunk."
        bind:value={chunk_overlap_tokens}
        validator={(value) =>
          number_validator({
            min: 0,
            max: chunk_size_tokens || undefined,
            integer: true,
            label: "Chunk Overlap",
            optional: false,
          })(value)}
      />
    </div>
  {/if}
</div>
