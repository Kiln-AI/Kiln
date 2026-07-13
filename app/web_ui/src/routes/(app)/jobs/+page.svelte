<script lang="ts">
  import AppPage from "../app_page.svelte"
  import JobsTable from "$lib/components/jobs_table.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Background Jobs",
    description:
      "Background job panel. Lists jobs with status, progress, and lifecycle controls.",
  })
</script>

<AppPage
  title="Jobs"
  subtitle="Background jobs with status, progress, and lifecycle controls."
>
  <JobsTable />
</AppPage>
