<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { number_validator } from "$lib/utils/input_validators"

  export let use_full_documents: boolean = true
  export let chunk_size_tokens: number | null = null
  export let chunk_overlap_tokens: number | null = null

  $: {
    if (use_full_documents) {
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
    id="use_full_documents_checkbox"
    inputType="checkbox"
    label="Use entire documents"
    description="Generate from whole documents without splitting into parts."
    info_description="For very long documents such as books, manuals, or transcripts, splitting into smaller parts helps create more focused content."
    bind:value={use_full_documents}
  />

  {#if !use_full_documents}
    <div class="pl-6 space-y-3 border-l-2 border-base-300">
      <FormElement
        id="chunk_size_tokens"
        inputType="input_number"
        label="Part size (tokens)"
        description="Approximate number of tokens per part"
        info_description="Smaller parts allow for more granular processing, but may not encapsulate broader context."
        bind:value={chunk_size_tokens}
        validator={(value) =>
          number_validator({
            min: 1,
            integer: true,
            label: "Part Size",
            optional: false,
          })(value)}
      />
      <FormElement
        id="chunk_overlap_tokens"
        inputType="input_number"
        label="Part overlap (tokens)"
        description="Number of tokens to overlap between parts"
        info_description="Overlap ensures sentences that span boundaries aren't lost because they're fully contained in at least one part."
        bind:value={chunk_overlap_tokens}
        validator={(value) =>
          number_validator({
            min: 0,
            max: chunk_size_tokens || undefined,
            integer: true,
            label: "Part Overlap",
            optional: false,
          })(value)}
      />
    </div>
  {/if}
</div>
