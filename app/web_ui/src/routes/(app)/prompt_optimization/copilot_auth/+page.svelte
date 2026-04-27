<script lang="ts">
  import { ui_state } from "$lib/stores"
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Prompt Optimization Copilot Auth",
    description:
      "Authentication page for Kiln Copilot access to create optimized prompts.",
  })

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id
</script>

<CopilotAuthPage
  title="Create Optimized Prompt"
  docs_link="https://docs.kiln.tech/docs/prompts"
  breadcrumbs={[
    { label: "Optimize", href: `/optimize/${project_id}/${task_id}` },
    { label: "Prompts", href: `/prompts/${project_id}/${task_id}` },
  ]}
  success_redirect_url={`/prompt_optimization/${project_id}/${task_id}/create_prompt_optimization_job`}
/>
