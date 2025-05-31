<script lang="ts">
  import { page } from "$app/stores"
  import { projects } from "$lib/stores"
  import { _ } from "svelte-i18n"
  import AppPage from "../../../app_page.svelte"

  import EditProject from "../../../../(fullscreen)/setup/(setup)/create_project/edit_project.svelte"

  $: project_id = $page.params.slug
  $: project = $projects?.projects.find((p) => p.id == project_id)
</script>

<div class="max-w-[800px]">
  <AppPage title={$_("project.edit_project")} subtitle={project?.name}>
    <EditProject {project} />
  </AppPage>
</div>
