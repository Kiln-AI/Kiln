<script lang="ts">
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { mime_type_to_string } from "$lib/utils/formatters"

  export let extractor: string | null = null
  export let label: string = "Extractor"
  export let description: string | undefined = undefined
  export let info_description: string | undefined = undefined
  export let error_message: string | null = null

  let extractor_options: OptionGroup[] = []

  onMount(async () => {
    const { data, error } = await client.GET("/api/available_extractors")
    if (error) {
      console.error(error)
      extractor_options = []
      return
    }

    const options: OptionGroup[] = []
    for (const provider of data) {
      const opts = (provider.extractors || []).map((ex) => {
        const value = provider.provider_id + "/" + ex.id
        let description: string | undefined = undefined
        const mime_types = ex.supported_mime_types || []
        if (mime_types.length) {
          description =
            "Supports " +
            mime_types.map((m) => mime_type_to_string(m)).join(", ")
        }
        return {
          value,
          label: ex.name,
          description,
        }
      })
      if (opts.length > 0) {
        options.push({ label: provider.provider_name, options: opts })
      }
    }
    extractor_options = options
  })
</script>

<div>
  <FormElement
    {label}
    {description}
    {info_description}
    bind:value={extractor}
    id="extractor"
    inputType="fancy_select"
    bind:error_message
    fancy_select_options={extractor_options}
    placeholder="Select an extractor"
  />
</div>
