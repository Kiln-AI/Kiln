<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import { onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"

  // ### Spec Creation Form ###

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_type: SpecType = "behaviour"
  let spec_template: string | undefined = undefined
  let spec_definition: string | undefined = undefined
  let name = ""

  let tool_function_name: string | undefined = undefined

  onMount(() => {
    const spec_type_param = $page.url.searchParams.get("type")
    if (spec_type_param) {
      spec_type = spec_type_param as SpecType
    }
    name = formatSpecTypeName(spec_type)
    spec_template = $page.url.searchParams.get("template") || undefined
    spec_definition = spec_template
    tool_function_name =
      $page.url.searchParams.get("tool_function_name") || undefined
  })

  let create_error: KilnError | null = null
  let submitting = false
  let complete = false

  let analyze_dialog: Dialog | null = null
  async function analyze_spec() {
    analyze_dialog?.show()
    submitting = false
  }

  async function create_spec() {
    try {
      create_error = null
      submitting = true
      complete = false
      if (!spec_definition) {
        throw createKilnError("Spec definition is required")
      }
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec",
        {
          params: {
            path: { project_id, task_id },
          },
          body: {
            name,
            definition: spec_definition,
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

<div class="max-w-[900px]">
  <AppPage
    title="Define Spec"
    subtitle={`Template: ${formatSpecTypeName(spec_type)}`}
    breadcrumbs={[
      {
        label: "Specs",
        href: `/specs/${project_id}/${task_id}`,
      },
      {
        label: "Spec Templates",
        href: `/specs/${project_id}/${task_id}/select_template`,
      },
    ]}
  >
    <FormContainer
      submit_label="Next"
      on:submit={analyze_spec}
      bind:error={create_error}
      bind:submitting
      warn_before_unload={!!(!complete && (spec_definition || name))}
    >
      {#if tool_function_name}
        <span class="text-sm text-gray-500"
          >Tool Function Name: {tool_function_name}</span
        >
      {/if}
      <FormElement
        label="Spec Name"
        description="A short name for your own reference."
        id="spec_name"
        bind:value={name}
      />
      <FormElement
        label="Spec Definition"
        description="A detailed definition of the spec. This will be used by AI when evaluating if your model meets the spec requirements."
        id="definition"
        inputType="textarea"
        height="xl"
        bind:value={spec_definition}
        inline_action={{
          handler: () => {
            spec_definition = spec_template
          },
          label: "Reset",
        }}
      />
      <Warning
        warning_message="Next we'll analyze your spec to ensure it's clear and actionable for an AI judge. You'll have a chance to review and refine it before creating the spec."
        warning_color="warning"
        warning_icon="exclaim"
      />
    </FormContainer>
    <div class="flex flex-row gap-1 mt-2 justify-end">
      <span class="text-xs text-gray-500">or</span>
      <button
        class="link underline text-xs text-gray-500"
        on:click={create_spec}>Create Spec Without Analysis</button
      >
    </div>
  </AppPage>
</div>

<Dialog bind:this={analyze_dialog} title="Analyzing Spec">
  <div class="flex flex-col items-center justify-center min-h-[100px]">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
</Dialog>
