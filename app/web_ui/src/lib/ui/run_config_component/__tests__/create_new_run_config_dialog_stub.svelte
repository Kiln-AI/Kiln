<script lang="ts">
  import type { Task, TaskRunConfig } from "$lib/types"

  export let project_id: string
  export let task: Task | null
  export let new_run_config_created:
    | ((run_config: TaskRunConfig) => void)
    | null = null

  export function show() {}
  export function showClone(run_config: TaskRunConfig) {
    void run_config
  }
  export function close() {}
</script>

<!-- Stands in for CreateNewRunConfigDialog, whose run config picker loads
     models and prompts over the network when it mounts. -->
<div
  data-testid="create-new-run-config-dialog-stub"
  data-project-id={project_id}
  data-task-id={task?.id ?? ""}
  data-has-created-callback={new_run_config_created !== null}
></div>
