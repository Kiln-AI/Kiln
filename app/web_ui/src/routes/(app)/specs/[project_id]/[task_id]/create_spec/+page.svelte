<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import type { SpecType } from "$lib/types"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import UndesiredBehaviourForm from "./forms/undesired_behaviour_form.svelte"
  import ToolUseForm from "./forms/tool_use_form.svelte"
  import CreateSpecForm from "./forms/create_spec_form.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_type: SpecType = "desired_behaviour"
  $: {
    const type_param = $page.url.searchParams.get("type")
    if (type_param) {
      spec_type = type_param as SpecType
    }
  }
  $: spec_description = $page.url.searchParams.get("description") || undefined
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
    {#if spec_type === "undesired_behaviour"}
      <UndesiredBehaviourForm />
    {:else if spec_type === "appropriate_tool_use"}
      <ToolUseForm />
    {:else if spec_type === "reference_answer_accuracy"}
      <CreateSpecForm spec_type="reference_answer_accuracy" />
    {/if}
  </AppPage>
</div>
