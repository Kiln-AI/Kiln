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

  let spec_name = ""
  let spec_description = ""
  let spec_type: SpecType = "desired_behaviour"

  async function create_spec() {
    try {
      create_error = null
      create_loading = true
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec",
        {
          params: {
            path: { project_id, task_id },
          },
          body: {
            name: spec_name,
            description: spec_description,
            type: spec_type,
          },
        },
      )
      if (error) {
        throw error
      }
      if (data?.id) {
        goto(`/specs/${project_id}/${task_id}/${data.id}`)
      }
    } catch (error) {
      create_error = createKilnError(error)
    } finally {
      create_loading = false
    }
  }
</script>

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
  >
    <FormElement label="Spec Name" id="spec_name" bind:value={spec_name} />
    <FormElement
      label="Spec Description"
      id="spec_description"
      bind:value={spec_description}
    />
  </FormContainer>
</AppPage>
