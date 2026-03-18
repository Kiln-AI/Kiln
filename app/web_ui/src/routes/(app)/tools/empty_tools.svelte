<script lang="ts">
  import ToolsIcon from "$lib/ui/icons/tools_icon.svelte"
  import Intro from "$lib/ui/intro.svelte"

  export let project_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <div class="h-12 w-12">
        <ToolsIcon />
      </div>
    </div>
    <Intro
      title="Add Tools to Your Project"
      description_paragraphs={[
        "Tools can provide powerful capabilities to your AI tasks.",
        "Add search tools, MCP servers, or Kiln Tasks as tools to give your system new skills.",
      ]}
      action_buttons={[
        {
          label: "Add Tool",
          href: `/tools/${project_id}/add_tools`,
          is_primary: true,
        },
      ]}
    />
  </div>
</div>
