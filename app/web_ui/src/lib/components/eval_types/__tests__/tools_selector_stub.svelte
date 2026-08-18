<script lang="ts">
  import type { ToolsSelectorSettings } from "$lib/ui/run_config_component/tools_selector_settings"

  export let project_id: string = ""
  export let label: string = ""
  export let settings: Partial<ToolsSelectorSettings> = {}
  export let tools: string[] = []
</script>

<div
  data-testid="tools-selector-stub"
  data-project-id={project_id}
  data-label={label}
  data-sandbox-code-context={settings.sandbox_code_context ?? "none"}
  data-tools={JSON.stringify(tools)}
>
  <button
    type="button"
    data-testid="tools-selector-add"
    on:click={() => {
      tools = [...tools, "kiln_tool::llm_judge"]
    }}
  >
    add tool
  </button>
</div>
