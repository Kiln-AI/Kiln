<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import EditLocalTool from "./edit_local_tool.svelte"
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
</script>

<AppPage
  title="Connect Local MCP Server"
  subtitle="Connect to a local Model Context Protocol (MCP) server to add external
        tools to your project."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp#connecting-local-mcp-servers"
  breadcrumbs={[
    ...($ui_state.current_task_id
      ? [
          {
            label: "Optimize",
            href: `/optimize/${$page.params.project_id}/${$ui_state.current_task_id}`,
          },
        ]
      : []),
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
  <EditLocalTool />
</AppPage>
