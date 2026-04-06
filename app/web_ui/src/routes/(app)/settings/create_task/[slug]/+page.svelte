<script lang="ts">
  import { page } from "$app/stores"
  import AppPage from "../../../app_page.svelte"
  import EditTask from "../../../../(fullscreen)/setup/(setup)/create_task/edit_task.svelte"

  import { agentInfo } from "$lib/agent"
  let project_target_name: string | null = null
  $: project_id = $page.params.slug!
  $: agentInfo.set({
    name: "Create Task",
    description: `Create a new task in project ID ${project_id}. A task is a single goal for a model to accomplish.`,
  })
</script>

<div class="max-w-[900px]">
  <AppPage
    title="New Task"
    subtitle="A 'task' is a single goal for a model to accomplish."
    sub_subtitle="Target project: {project_target_name}"
  >
    <EditTask bind:project_target_name explicit_project_id={project_id} />
  </AppPage>
</div>
