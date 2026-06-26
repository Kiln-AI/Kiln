<script lang="ts">
  import AppPage from "../../../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { agentInfo } from "$lib/agent"
  import {
    ALL_V2_EVAL_TYPES,
    getV2EvalTypeMetadata,
    type V2EvalType,
  } from "$lib/utils/eval_types/registry"
  import EvalConfigBuilder from "$lib/components/eval_types/eval_config_builder.svelte"
  import { buildCreateEvalBreadcrumbs } from "../breadcrumbs"
  import { getCreateEvalLayoutContext } from "../context"

  const ctx = getCreateEvalLayoutContext()

  $: evaluator = $ctx_evaluator
  $: task = $ctx_task
  $: spec = $ctx_spec
  $: project_id = $ctx_project_id
  $: task_id = $ctx_task_id
  $: eval_id = $ctx_eval_id
  $: spec_id = $ctx_spec_id

  const ctx_evaluator = ctx.evaluator
  const ctx_task = ctx.task
  const ctx_spec = ctx.spec
  const ctx_project_id = ctx.project_id
  const ctx_task_id = ctx.task_id
  const ctx_eval_id = ctx.eval_id
  const ctx_spec_id = ctx.spec_id

  $: raw_type = $page.params.eval_config_type
  $: valid_type = ALL_V2_EVAL_TYPES.includes(raw_type as V2EvalType)
    ? (raw_type as V2EvalType)
    : null
  $: type_metadata = valid_type ? getV2EvalTypeMetadata(valid_type) : null

  $: agentInfo.set({
    name: "Create Eval Config",
    description: `Create a new eval configuration (${raw_type}) for eval ID ${eval_id}, spec ID ${spec_id} in project ID ${project_id}, task ID ${task_id}. Eval name: ${evaluator?.name ?? "[loading]"}.`,
  })

  $: base_breadcrumbs = buildCreateEvalBreadcrumbs(
    project_id,
    task_id,
    spec_id,
    eval_id,
    spec,
    $page.url.searchParams.get("next_page"),
  )

  $: breadcrumbs = [
    ...base_breadcrumbs,
    {
      label: "Add Judge",
      href: `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}/create_eval_config${$page.url.search}`,
    },
  ]
</script>

{#if !valid_type}
  <div class="max-w-[1400px]">
    <AppPage title="Unknown Eval Type" {breadcrumbs}>
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Unknown Eval Type</div>
        <div class="text-error text-sm">
          "{raw_type}" is not a recognized eval type. Please go back and select
          a valid type.
        </div>
      </div>
    </AppPage>
  </div>
{:else if evaluator && task}
  <div class="max-w-[1400px]">
    <AppPage
      title={type_metadata?.pageTitle ?? "Add a Judge"}
      subtitle={type_metadata?.pageSubtitle ?? ""}
      {breadcrumbs}
    >
      <EvalConfigBuilder
        eval_config_type={valid_type}
        {evaluator}
        {task}
        {spec}
        {project_id}
        {task_id}
        {eval_id}
        {spec_id}
      />
    </AppPage>
  </div>
{:else}
  <div class="max-w-[1400px]">
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  </div>
{/if}
