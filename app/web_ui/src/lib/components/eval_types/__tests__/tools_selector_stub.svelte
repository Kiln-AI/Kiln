<script lang="ts">
  import type { ToolsSelectorSettings } from "$lib/ui/run_config_component/tools_selector_settings"

  export let project_id: string = ""
<<<<<<< HEAD
=======
  // Recorded so a test can assert the code judge is given no task: a real
  // ToolsSelector with a task_id loads that task's saved tools over the bound
  // value, which would clobber a judge's tool allowlist.
  export let task_id: string | null = null
>>>>>>> 721c4941b
  export let label: string = ""
  export let settings: Partial<ToolsSelectorSettings> = {}
  export let tools: string[] = []
</script>

<div
  data-testid="tools-selector-stub"
  data-project-id={project_id}
<<<<<<< HEAD
  data-label={label}
  data-code-eval-context={settings.code_eval_context ? "true" : "false"}
=======
  data-task-id={task_id ?? ""}
  data-label={label}
  data-sandbox-code-context={settings.sandbox_code_context ?? "none"}
>>>>>>> 721c4941b
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
