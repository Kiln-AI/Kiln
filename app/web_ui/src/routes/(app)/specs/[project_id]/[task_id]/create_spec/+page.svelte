<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import UndesiredBehaviourForm from "./forms/undesired_behaviour_form.svelte"
  import ToolUseForm from "./forms/tool_use_form.svelte"
  import { onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecProperties, SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_type: SpecType = "desired_behaviour"
  let spec_template_description: string | undefined = undefined

  onMount(() => {
    const spec_type_param = $page.url.searchParams.get("type")
    if (spec_type_param) {
      spec_type = spec_type_param as SpecType
    }
    spec_template_description =
      $page.url.searchParams.get("template_description") || undefined
  })

  let form_has_unsaved_changes: boolean = false

  let name = ""
  let description = ""

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
            properties: form?.get_properties() as SpecProperties | null,
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

  let form: ToolUseForm | UndesiredBehaviourForm | null = null

  let suggestion_mode: boolean = true
</script>

<div class="max-w-[900px]">
  <AppPage
    title="{suggestion_mode ? 'Refine' : 'Define'} Spec"
    subtitle="Template: {formatSpecTypeName(spec_type)}"
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
      bind:submitting
      warn_before_unload={!!(!complete && form_has_unsaved_changes)}
    >
      {#if spec_type === "appropriate_tool_use"}
        <ToolUseForm bind:this={form} bind:form_has_unsaved_changes />
      {:else if spec_type === "undesired_behaviour"}
        <UndesiredBehaviourForm
          bind:this={form}
          bind:form_has_unsaved_changes
        />
      {/if}
    </FormContainer>
  </AppPage>
</div>
