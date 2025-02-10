<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import LoadTaskEditor from "../../../edit_task/[project_id]/[task_id]/load_task_editor.svelte"
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Clone Task"
    subtitle="Create a new task, using an existing task as a template"
    sub_subtitle="The cloned task will not contain any data from the original task."
  >
    <LoadTaskEditor clone_mode={true} />
  </AppPage>
</div>
