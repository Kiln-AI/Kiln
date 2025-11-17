<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import FormElement from "$lib/utils/form_element.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let create_error: KilnError | null = null
  let create_loading = false
  let complete = false

  let spec_name = ""
  let spec_description = ""
  let spec_definition = ""
  let spec_type: SpecType = "desired_behaviour"

  async function create_spec() {
    try {
      create_error = null
      create_loading = true
      complete = false
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec",
        {
          params: {
            path: { project_id, task_id },
          },
          body: {
            name: spec_name,
            description: spec_description,
            definition: spec_definition,
            type: spec_type,
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
      create_loading = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Define a Spec"
    subtitle="Define how you want your task to behave"
    breadcrumbs={[
      {
        label: "Specs",
        href: `/specs/${project_id}/${task_id}`,
      },
    ]}
  >
    <FormContainer
      submit_label="Create Spec"
      on:submit={create_spec}
      bind:error={create_error}
      bind:submitting={create_loading}
      warn_before_unload={!!(
        !complete &&
        (spec_name || spec_description || spec_definition)
      )}
    >
      <FormElement
        label="Spec Name"
        description="A short name for your own reference."
        id="spec_name"
        bind:value={spec_name}
      />
      <FormElement
        label="Spec Description"
        description="A description for your own reference."
        id="spec_description"
        bind:value={spec_description}
        inputType="textarea"
      />
      <FormElement
        label="Spec Definition"
        description="A detailed definition of the spec. This will be used by AI to understand the spec."
        id="spec_definition"
        inputType="textarea"
        bind:value={spec_definition}
      />
    </FormContainer>
  </AppPage>
</div>
