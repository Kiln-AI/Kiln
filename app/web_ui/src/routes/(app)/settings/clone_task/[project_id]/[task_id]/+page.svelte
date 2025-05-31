<script lang="ts">
  import { _ } from "svelte-i18n"
  import AppPage from "../../../../app_page.svelte"
  import LoadTaskEditor from "../../../edit_task/[project_id]/[task_id]/load_task_editor.svelte"
</script>

<div class="max-w-[900px]">
  <AppPage
    title={$_("task.clone_task")}
    subtitle={$_("task.clone_task_subtitle")}
    sub_subtitle={$_("task.clone_task_description")}
  >
    <LoadTaskEditor clone_mode={true} />
  </AppPage>
</div>
