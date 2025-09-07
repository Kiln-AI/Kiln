<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import EditLocalTool from "./edit_local_tool.svelte"
</script>

<AppPage
  title="Connect Local MCP Server"
  subtitle="Connect to a local Model Context Protocol (MCP) server to add external
        tools to your project."
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
  <EditLocalTool />
</AppPage>
