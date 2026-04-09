<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import EditProject from "../../../(fullscreen)/setup/(setup)/create_project/edit_project.svelte"
</script>

<div class="max-w-[600px]">
  <AppPage
    title="Add Project"
    subtitle="Projects are a collection of tasks, results, evals, and other resources."
  >
    <EditProject
      redirect_on_created="/settings/create_task"
      import_link="/settings/import_project"
    />
  </AppPage>
</div>
