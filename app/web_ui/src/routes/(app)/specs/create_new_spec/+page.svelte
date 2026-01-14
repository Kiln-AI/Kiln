<script lang="ts">
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"
  import { ui_state } from "$lib/stores"

  onMount(async () => {
    const project_id = $ui_state.current_project_id
    const task_id = $ui_state.current_task_id
    if (project_id && task_id) {
      goto(`/specs/${project_id}/${task_id}/select_template`)
    } // else redirect to select task page? or maybe it will if you pass in null above?
  })
</script>
