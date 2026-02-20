<script lang="ts">
  import { ui_state } from "$lib/stores"
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id
</script>

<CopilotAuthPage
  title="Create Spec"
  docs_link="https://docs.kiln.tech/docs/evals-and-specs"
  breadcrumbs={[
    { label: "Specs & Evals", href: `/specs/${project_id}/${task_id}` },
  ]}
  success_redirect_url={`/specs/${project_id}/${task_id}/select_template`}
  cancel_redirect_url={`/specs/${project_id}/${task_id}/select_workflow`}
/>
