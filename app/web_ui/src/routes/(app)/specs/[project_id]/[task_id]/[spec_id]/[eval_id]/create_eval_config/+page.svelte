<script lang="ts">
  import AppPage from "../../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { agentInfo } from "$lib/agent"
  import {
    ALL_V2_EVAL_TYPES,
    getV2EvalTypeMetadata,
    type V2EvalType,
  } from "$lib/utils/eval_types/registry"
  import { buildCreateEvalBreadcrumbs } from "./breadcrumbs"
  import { getCreateEvalLayoutContext } from "./context"
  import EvalTypeRow from "$lib/components/eval_types/select/eval_type_row.svelte"

  const ctx = getCreateEvalLayoutContext()

  $: evaluator = $ctx_evaluator
  $: spec = $ctx_spec
  $: project_id = $ctx_project_id
  $: task_id = $ctx_task_id
  $: eval_id = $ctx_eval_id
  $: spec_id = $ctx_spec_id

  const ctx_evaluator = ctx.evaluator
  const ctx_spec = ctx.spec
  const ctx_project_id = ctx.project_id
  const ctx_task_id = ctx.task_id
  const ctx_eval_id = ctx.eval_id
  const ctx_spec_id = ctx.spec_id

  $: agentInfo.set({
    name: "Create Eval Config",
    description: `Create a new eval configuration for eval ID ${eval_id}, spec ID ${spec_id} in project ID ${project_id}, task ID ${task_id}. Eval name: ${evaluator?.name ?? "[loading]"}.`,
  })

  $: breadcrumbs = buildCreateEvalBreadcrumbs(
    project_id,
    task_id,
    spec_id,
    eval_id,
    spec,
    $page.url.searchParams.get("next_page"),
  )

  const recommendedType = ALL_V2_EVAL_TYPES[0]

  function preserved_query_string(): string {
    const params = new URLSearchParams()
    const next_page = $page.url.searchParams.get("next_page")
    const save_as_default = $page.url.searchParams.get("save_as_default")
    if (next_page) params.set("next_page", next_page)
    if (save_as_default) params.set("save_as_default", save_as_default)
    const qs = params.toString()
    return qs ? "?" + qs : ""
  }

  function select_v2_type(type: V2EvalType) {
    const base = $page.url.pathname.replace(/\/$/, "")
    goto(`${base}/${type}${preserved_query_string()}`)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Select a Judge Type"
    subtitle="Every type produces the same scores — it just changes how they're computed."
    {breadcrumbs}
  >
    <div class="pt-6 max-w-3xl">
      <div class="flex flex-col gap-2">
        {#each ALL_V2_EVAL_TYPES as evalType}
          {@const metadata = getV2EvalTypeMetadata(evalType)}
          <EvalTypeRow
            {evalType}
            {metadata}
            recommended={evalType === recommendedType}
            on:select={() => select_v2_type(evalType)}
          />
        {/each}
      </div>
    </div>
  </AppPage>
</div>
