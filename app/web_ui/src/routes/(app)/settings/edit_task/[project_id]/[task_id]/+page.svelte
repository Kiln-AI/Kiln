<script lang="ts">
  import LoadTaskEditor from "./load_task_editor.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import { ui_state } from "$lib/stores"
  import { get } from "svelte/store"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Edit Task",
    description: `Edit task ID ${task_id} in project ID ${project_id}. Modify task prompt, requirements, and configuration.`,
  })

  let delete_dialog: DeleteDialog | null = null
  let saved: boolean = false
  $: delete_url = `/api/projects/${project_id}/tasks/${task_id}`
  function after_delete() {
    // This prevents the page from showing the "are you sure you want to leave, changes will be lost" message.
    // It's already deleted so it's misleading.
    saved = true
    // Remove the current task from the UI state, as it doesn't exist
    ui_state.set({
      ...get(ui_state),
      current_task_id: null,
    })
    goto(`/setup/select_task`)
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Edit Task"
    subtitle={task_id ? `Task ID: ${task_id}` : undefined}
    breadcrumbs={[{ label: "Settings", href: "/settings" }]}
    action_buttons={[
      {
        icon: "/images/delete.svg",
        handler: () => delete_dialog?.show(),
      },
      {
        label: "Clone Task",
        handler: () => {
          goto(`/settings/clone_task/${project_id}/${task_id}`)
        },
      },
    ]}
  >
    <LoadTaskEditor bind:saved />
  </AppPage>
</div>

<DeleteDialog
  name="Task"
  bind:this={delete_dialog}
  {delete_url}
  {after_delete}
/>
