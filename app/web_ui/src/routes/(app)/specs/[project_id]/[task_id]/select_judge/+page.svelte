<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import AppPage from "../../../../app_page.svelte"
  import OptionList from "$lib/ui/option_list.svelte"
  import { buildEvalTypeOptions } from "$lib/components/eval_types/select/eval_type_options"
  import type { V2EvalType } from "$lib/utils/eval_types/registry"
  import type { SpecType } from "$lib/types"
  import { parseSpecWorkflow, spec_builder_url } from "../spec_utils"
  import { agentInfo } from "$lib/agent"

  // ### Judge Type Select ###
  //
  // Sits between the template picker and the spec builder. Only the desired
  // behaviour and issue templates route here; every other template's judge is
  // implied, so they skip straight to the builder.

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: spec_type = $page.url.searchParams.get("type") as SpecType | null
  $: workflow = parseSpecWorkflow($page.url.searchParams.get("workflow"))
  $: agentInfo.set({
    name: "Select Judge Type",
    description: `Select the judge type for a new eval in project ID ${project_id}, task ID ${task_id}. Choose how each output gets scored.`,
  })

  const eval_type_options = buildEvalTypeOptions()

  // Landing here without a template means the flow was entered mid-way (e.g. a
  // stale bookmark). Send them back to pick one rather than rendering a picker
  // that can't build a spec.
  onMount(() => {
    if (!spec_type) {
      goto(
        `/specs/${project_id}/${task_id}/select_template?workflow=${workflow}`,
      )
    }
  })

  function select_option(id: string) {
    if (!spec_type) return
    goto(
      spec_builder_url(
        project_id,
        task_id,
        spec_type,
        workflow,
        id as V2EvalType,
      ),
    )
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Select a Judge Type"
    subtitle="Choose how each output gets scored."
    breadcrumbs={[
      {
        label: "Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
      {
        label: "Eval Templates",
        href: `/specs/${project_id}/${task_id}/select_template?workflow=${workflow}`,
      },
    ]}
  >
    <!-- Without a template this page is redirecting (see onMount); don't flash
      a picker that can't build an eval in the meantime. -->
    {#if spec_type}
      <div class="pt-6 max-w-3xl">
        <OptionList options={eval_type_options} {select_option} />
      </div>
    {/if}
  </AppPage>
</div>
