<script lang="ts">
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"
  import { agentInfo } from "$lib/agent"
  import { spec_builder_url } from "../[project_id]/[task_id]/spec_utils"
  import type { SpecType } from "$lib/types"
  import type { V2EvalType } from "$lib/utils/eval_types/registry"

  agentInfo.set({
    name: "Evals Kiln Pro Auth",
    description: "Authentication page for Kiln Pro access to create evals.",
  })

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id

  // The workflow screen sends the already-chosen template and judge along, so
  // a successful connect drops the user into the spec builder in pro mode.
  // Without them (stale bookmark), restart at the type picker — or the home
  // page if ui_state has no current project/task to build a URL from.
  $: spec_type = $page.url.searchParams.get("type") as SpecType | null
  $: judge = $page.url.searchParams.get("judge") as V2EvalType | null
  $: success_redirect_url =
    spec_type && judge && project_id && task_id
      ? spec_builder_url(project_id, task_id, spec_type, "pro", judge)
      : project_id && task_id
        ? `/specs/${project_id}/${task_id}/select_template`
        : "/"
</script>

<CopilotAuthPage
  title="Create Eval"
  docs_link="https://docs.kiln.tech/docs/evals-and-specs"
  breadcrumbs={[{ label: "Evals", href: `/specs/${project_id}/${task_id}` }]}
  {success_redirect_url}
/>
