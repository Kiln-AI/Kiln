<script lang="ts">
  import { ui_state } from "$lib/stores"
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id
</script>

<CopilotAuthPage
  title="Create Optimized Prompt"
  docs_link="https://docs.kiln.tech/docs/prompts"
  breadcrumbs={[
    { label: "Optimize", href: `/optimize/${project_id}/${task_id}` },
    { label: "Prompts", href: `/prompts/${project_id}/${task_id}` },
    { label: "Optimizer Jobs", href: `/gepa/${project_id}/${task_id}` },
  ]}
  success_redirect_url="/gepa/{project_id}/{task_id}/create_gepa"
  cancel_redirect_url="/gepa/{project_id}/{task_id}/create_gepa"
/>
