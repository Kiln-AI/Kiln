<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import EditRemoteTool from "./edit_remote_tool.svelte"
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
</script>

<AppPage
  title="Connect Remote MCP Server"
  subtitle="Connect to a remote Model Context Protocol (MCP) server to add external
        tools to your project."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp#connecting-remote-mcp-servers"
  breadcrumbs={[
    {
      label: "Optimize",
      href: `/optimize/${$page.params.project_id}/${$ui_state.current_task_id}`,
    },
    {
      label: "Tools",
      href: `/tools/${$page.params.project_id}`,
    },
    {
      label: "Add Tools",
      href: `/tools/${$page.params.project_id}/add_tools`,
    },
  ]}
>
  <EditRemoteTool />
</AppPage>
