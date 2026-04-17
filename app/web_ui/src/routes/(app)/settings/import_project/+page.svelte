<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import ImportProject from "$lib/components/import/import_project.svelte"
  import { goto } from "$app/navigation"
  import { agentInfo } from "$lib/agent"
  agentInfo.set({
    name: "Import Project",
    description:
      "Import an existing Kiln project, either from a local folder or a remote Git repository.",
  })
</script>

<AppPage
  title="Import Project"
  subtitle="Import an existing Kiln project"
  breadcrumbs={[
    { label: "Settings", href: "/settings" },
    { label: "Manage Projects", href: "/settings/manage_projects" },
  ]}
>
  <ImportProject
    create_link="/settings/create_project"
    on_complete={() => goto("/settings/manage_projects")}
  />
</AppPage>
