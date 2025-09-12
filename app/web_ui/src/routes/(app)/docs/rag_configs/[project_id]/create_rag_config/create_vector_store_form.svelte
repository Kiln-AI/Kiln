<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { createEventDispatcher } from "svelte"
  import type { VectorStoreType } from "$lib/types"
  import { number_validator } from "$lib/utils/input_validators"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string = ""
  let description: string = ""
  let selectedStoreType: VectorStoreType | null = null

  // Properties for all vector store types
  let similarity_top_k: number = 10

  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { vector_store_config_id: string }
  }>()

  const storeTypeOptions: OptionGroup[] = [
    {
      label: "Vector Store Types",
      options: [
        {
          label: "LanceDB - Full Text Search",
          value: "lancedb_fts",
          description:
            "Search using text matching only - fastest for keyword searches",
        },
        {
          label: "LanceDB - Vector Search",
          value: "lancedb_vector",
          description:
            "Search using semantic similarity vectors - best for meaning-based searches",
        },
        {
          label: "LanceDB - Hybrid Search",
          value: "lancedb_hybrid",
          description:
            "Combines text and vector search - best overall accuracy",
        },
      ],
    },
  ]

  async function create_vector_store_config() {
    try {
      loading = true
      error = null

      if (!selectedStoreType) {
        error = createKilnError({
          message: "Please select a vector store type.",
          status: 400,
        })
        return
      }

      const properties: Record<string, string | number | boolean> = {
        similarity_top_k,
      }

      const { error: create_error, data } = await client.POST(
        "/api/projects/{project_id}/create_vector_store_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: name || null,
            description: description || null,
            store_type: selectedStoreType,
            properties,
          },
        },
      )

      if (create_error) {
        error = createKilnError(create_error)
        return
      }

      if (data?.id) {
        dispatch("success", { vector_store_config_id: data.id })
      }
    } finally {
      loading = false
    }
  }
</script>

<FormContainer
  submit_visible={true}
  submit_label="Create Vector Store"
  on:submit={create_vector_store_config}
  {error}
  gap={4}
  bind:submitting={loading}
  {keyboard_submit}
>
  <FormElement
    id="store_type_select"
    label="Vector Store Type"
    description="Choose how documents will be searched"
    info_description="Full text search is fastest for keyword searches, vector search is best for semantic meaning, and hybrid combines both approaches."
    fancy_select_options={storeTypeOptions}
    bind:value={selectedStoreType}
    inputType="fancy_select"
  />

  <FormElement
    label="Top K"
    description="The number of top search results to return"
    inputType="input_number"
    id="similarity_top_k"
    bind:value={similarity_top_k}
    validator={number_validator({ min: 1, label: "Results to Return" })}
  />

  <!-- Advanced Options -->
  <div class="collapse collapse-arrow bg-base-200">
    <input type="checkbox" />
    <div class="collapse-title text-sm font-medium">Advanced Options</div>
    <div class="collapse-content">
      <div class="flex flex-col gap-4">
        <FormElement
          label="Vector Store Name"
          description="A name to identify this configuration. Leave blank and we'll generate one for you."
          optional={true}
          inputType="input"
          id="vector_store_name"
          bind:value={name}
        />

        <FormElement
          label="Description"
          description="A description of the vector store configuration for your reference."
          optional={true}
          inputType="textarea"
          id="vector_store_description"
          bind:value={description}
        />
      </div>
    </div>
  </div>
</FormContainer>
