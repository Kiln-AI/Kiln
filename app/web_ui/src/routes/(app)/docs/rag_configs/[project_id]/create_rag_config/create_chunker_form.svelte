<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createEventDispatcher } from "svelte"
  import Collapse from "$lib/ui/collapse.svelte"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string = ""
  let description: string = ""
  let chunk_size: number = 1000
  let chunk_overlap: number = 200
  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { chunker_config_id: string }
  }>()

  async function create_chunker_config() {
    try {
      loading = true
      const { error: create_chunker_error, data } = await client.POST(
        "/api/projects/{project_id}/create_chunker_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: name || null,
            description: description || null,
            chunker_type: "fixed_window",
            properties: {
              chunk_size: chunk_size,
              chunk_overlap: chunk_overlap,
            },
          },
        },
      )

      if (create_chunker_error) {
        error = createKilnError(create_chunker_error)
        return
      }

      dispatch("success", { chunker_config_id: data.id || "" })
    } finally {
      loading = false
    }
  }
</script>

<FormContainer
  submit_visible={true}
  submit_label="Create Chunker"
  on:submit={async () => {
    await create_chunker_config()
  }}
  {error}
  gap={4}
  bind:submitting={loading}
  {keyboard_submit}
>
  <div class="flex flex-col gap-4">
    <FormElement
      label="Chunk Size"
      description="The number of tokens in each chunk."
      inputType="input_number"
      id="chunk_size"
      bind:value={chunk_size}
    />
    <FormElement
      label="Chunk Overlap"
      description="The number of tokens to overlap between chunks."
      inputType="input_number"
      id="chunk_overlap"
      bind:value={chunk_overlap}
    />
  </div>
  <Collapse title="Advanced Options">
    <FormElement
      label="Chunker Name"
      description="Leave blank and we'll generate one for you."
      optional={true}
      inputType="input"
      id="name"
      bind:value={name}
    />
    <FormElement
      label="Description"
      description="A description of the chunker for you and your team. This will have no effect on the chunker's behavior."
      optional={true}
      inputType="textarea"
      id="description"
      bind:value={description}
    />
  </Collapse>
</FormContainer>
