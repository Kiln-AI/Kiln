<script lang="ts">
  import { page } from "$app/stores"
  import { projects } from "$lib/stores"
  import AppPage from "../../../app_page.svelte"

  import EditProject from "../../../../(fullscreen)/setup/(setup)/create_project/edit_project.svelte"

  $: project_id = $page.params.slug
  $: project = $projects?.projects.find((p) => p.id == project_id)
</script>

<div class="max-w-[800px]">
  <AppPage
    title="Edit Project"
    subtitle={project?.name}
    breadcrumbs={[{ label: "Settings", href: "/settings" }]}
  >
    <EditProject {project} />
  </AppPage>
</div>
