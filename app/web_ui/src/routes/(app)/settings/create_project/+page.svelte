<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import EditProject from "../../../(fullscreen)/setup/(setup)/create_project/edit_project.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Create Project",
    description:
      "Create a new project. Projects are a collection of tasks, results, evals, and other resources.",
  })
</script>

<div class="max-w-[600px]">
  <AppPage
    title="Add Project"
    subtitle="Projects are a collection of tasks, results, evals, and other resources."
  >
    <EditProject redirect_on_created="/settings/create_task" />
  </AppPage>
</div>
