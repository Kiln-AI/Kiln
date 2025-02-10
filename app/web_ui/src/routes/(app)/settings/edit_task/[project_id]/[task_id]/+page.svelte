<script lang="ts">
  import LoadTaskEditor from "./load_task_editor.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Edit Task"
    subtitle={task_id ? `Task ID: ${task_id}` : undefined}
    action_buttons={[
      {
        label: "Clone Task",
        primary: true,
        handler: () => {
          goto(`/settings/clone_task/${project_id}/${task_id}`)
        },
      },
    ]}
  >
    <LoadTaskEditor />
  </AppPage>
</div>
