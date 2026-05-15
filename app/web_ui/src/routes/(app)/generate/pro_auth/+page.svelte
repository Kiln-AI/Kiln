<script lang="ts">
  import { ui_state } from "$lib/stores"
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Data Guide Kiln Pro Auth",
    description:
      "Authentication page for Kiln Pro access to draft a Data Guide.",
  })

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id
</script>

<CopilotAuthPage
  title="Set Up Data Guide with Kiln Pro"
  docs_link="https://docs.kiln.tech/docs/synthetic-data-generation"
  breadcrumbs={[
    {
      label: "Synthetic Data Generation",
      href: `/generate/${project_id}/${task_id}/synth`,
    },
  ]}
  success_redirect_url={`/generate/${project_id}/${task_id}/data_guide_setup_copilot`}
/>
