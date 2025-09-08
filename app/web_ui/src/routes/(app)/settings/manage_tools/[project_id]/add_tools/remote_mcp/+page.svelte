<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import EditRemoteTool from "./edit_remote_tool.svelte"
  import { page } from "$app/stores"
</script>

<AppPage
  title="Connect Remote MCP Server"
  subtitle="Connect to a remote Model Context Protocol (MCP) server to add external
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
  <EditRemoteTool />
</AppPage>
