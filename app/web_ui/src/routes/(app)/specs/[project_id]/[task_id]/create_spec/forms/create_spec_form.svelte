<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecProperties, SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import FormElement from "$lib/utils/form_element.svelte"

  export let spec_type: SpecType
  export let form_has_unsaved_changes: boolean = false
  export let get_properties: (() => SpecProperties) | undefined = undefined

  let name = ""
  let description = ""

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let create_error: KilnError | null = null
  let submitting = false
  let complete = false

  async function create_spec() {
    try {
      create_error = null
      submitting = true
      complete = false
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec",
        {
          params: {
            path: { project_id, task_id },
          },
          body: {
            name,
            description,
            properties: get_properties ? get_properties() : null,
            type: spec_type,
            priority: 1,
            status: "active",
            tags: [],
            eval_id: null,
          },
        },
      )
      if (error) {
        throw error
      }
      if (data?.id) {
        complete = true
        goto(`/specs/${project_id}/${task_id}/${data.id}`)
      }
    } catch (error) {
      create_error = createKilnError(error)
    } finally {
      submitting = false
    }
  }
</script>

<FormContainer
  submit_label="Create Spec"
  on:submit={create_spec}
  bind:error={create_error}
  bind:submitting
  warn_before_unload={!!(
    !complete &&
    form_has_unsaved_changes &&
    name &&
    description
  )}
>
  <FormElement
    label="Spec Name"
    description="A short name for your own reference."
    id="spec_name"
    bind:value={name}
  />
  <FormElement
    label="Spec Description"
    description="A short description for your own reference."
    id="spec_description"
    bind:value={description}
  />
  <slot name="form_elements" />
</FormContainer>
