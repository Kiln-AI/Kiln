<script lang="ts">
  import { ui_state } from "$lib/stores"
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Evals Kiln Pro Auth",
    description: "Authentication page for Kiln Pro access to create evals.",
  })

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id
</script>

<CopilotAuthPage
  title="Create Eval"
  docs_link="https://docs.kiln.tech/docs/evals-and-specs"
  breadcrumbs={[{ label: "Evals", href: `/specs/${project_id}/${task_id}` }]}
  success_redirect_url={`/specs/${project_id}/${task_id}/select_template`}
/>
