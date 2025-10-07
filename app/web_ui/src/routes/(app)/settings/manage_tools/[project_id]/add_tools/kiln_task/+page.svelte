<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import AddKilnTaskTool from "./add_kiln_task_tool.svelte"
  import { page } from "$app/stores"
</script>

<AppPage
  title="Create Tool from Kiln Task"
  subtitle="Allow your tasks to call another Kiln task, as a tool call."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/agents#multi-actor-interaction-aka-subtasks"
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
