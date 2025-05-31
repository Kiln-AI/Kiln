<script lang="ts">
  import { page } from "$app/stores"
  import { _ } from "svelte-i18n"
  import AppPage from "../../../app_page.svelte"
  import EditTask from "../../../../(fullscreen)/setup/(setup)/create_task/edit_task.svelte"

  let project_target_name: string | null = null
  $: project_id = $page.params.slug
</script>

<div class="max-w-[900px]">
  <AppPage
    title={$_("task.new_task")}
    subtitle={$_("task.new_task_description")}
    sub_subtitle="{$_('task.target_project')}: {project_target_name}"
  >
    <EditTask bind:project_target_name explicit_project_id={project_id} />
  </AppPage>
</div>
