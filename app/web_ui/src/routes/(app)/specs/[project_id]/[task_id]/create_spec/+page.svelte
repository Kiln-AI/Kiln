<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import FormElement from "$lib/utils/form_element.svelte"
  import { formatSpecTypeName } from "$lib/utils/formatters"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let create_error: KilnError | null = null
  let create_loading = false
  let complete = false

  let name = ""
  let definition = ""
  let spec_type: SpecType = "behaviour"
  $: {
    const type_param = $page.url.searchParams.get("type")
    if (type_param) {
      spec_type = type_param as SpecType
    }
  }
  $: spec_description = $page.url.searchParams.get("description") || undefined

  async function create_spec() {
    try {
      create_error = null
      create_loading = true
      complete = false
      if (spec_type !== "behaviour") {
        throw createKilnError("Not implemented yet")
      }
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec",
        {
          params: {
            path: { project_id, task_id },
          },
          body: {
            name,
            definition,
            properties: {
              spec_type: spec_type,
              base_instruction:
                "The model must follow the specified behaviour requirements.",
              behavior_description: definition,
              correct_behavior_examples: null,
              incorrect_behavior_examples: null,
            },
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
      create_loading = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create New Spec: {formatSpecTypeName(spec_type)}"
    subtitle={spec_description}
    breadcrumbs={[
      {
        label: "Specs",
        href: `/specs/${project_id}/${task_id}`,
      },
      {
        label: "Spec Templates",
        href: `/specs/${project_id}/${task_id}/create_spec/template_select`,
      },
    ]}
  >
    <FormContainer
      submit_label="Create Spec"
      on:submit={create_spec}
      bind:error={create_error}
      bind:submitting={create_loading}
      warn_before_unload={!!(!complete && (name || definition))}
    >
      <FormElement
        label="Spec Name"
        description="A short name for your own reference."
        id="spec_name"
        bind:value={name}
      />
      <FormElement
        label="Spec Definition"
        description="A detailed definition of the spec."
        id="spec_description"
        inputType="textarea"
        bind:value={definition}
      />
    </FormContainer>
  </AppPage>
</div>
