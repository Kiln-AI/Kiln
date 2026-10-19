<script lang="ts">
  import { ui_state } from "$lib/stores"
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Synthetic Data Kiln Pro Auth",
    description:
      "Authentication page for Kiln Pro access to generate a synthetic data batch.",
  })

  // Static route (no project/task in the path) so the Kinde OAuth redirect_uri
  // is a fixed URL. The destination is resolved from the current project/task.
  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id
</script>

<CopilotAuthPage
  title="Generate Synthetic Data Batch"
  subtitle="Kiln Pro plans and generates a diverse batch of synthetic data for your task."
  docs_link="https://docs.kiln.tech/docs/synthetic-data-generation"
  breadcrumbs={[
    {
      label: "Synthetic Data Generation",
      href: `/generate/${project_id}/${task_id}/synth?session_continued=true`,
    },
  ]}
  success_redirect_url={`/generate/${project_id}/${task_id}/synth?batch=pro&session_continued=true`}
/>
