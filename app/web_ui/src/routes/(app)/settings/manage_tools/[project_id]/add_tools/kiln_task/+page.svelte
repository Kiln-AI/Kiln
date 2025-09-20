<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import AddKilnTaskTool from "./add_kiln_task_tool.svelte"
  import { page } from "$app/stores"
</script>

<AppPage
  title="Add Kiln Task"
  subtitle="Add an existing Kiln Task as a tool to your project."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp#connecting-kiln-tasks"
  breadcrumbs={[
    {
      label: "Settings",
      href: `/settings`,
    },
    {
      label: "Manage Tools",
      href: `/settings/manage_tools/${$page.params.project_id}`,
    },
    {
      label: "Add Tools",
      href: `/settings/manage_tools/${$page.params.project_id}/add_tools`,
    },
  ]}
>
  <AddKilnTaskTool />
</AppPage>
