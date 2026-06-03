<script lang="ts">
  import RunConfigComponent from "../run_config_component.svelte"
  import type { Task } from "$lib/types"

  export let project_id: string
  export let current_task: Task
  export let pending_run_config_id: string | null = null
  export let model: string = ""
  export let selected_run_config_id: string | null = null
</script>

<div data-testid="selected">{selected_run_config_id}</div>
<div data-testid="model">{model}</div>

<RunConfigComponent
  bind:model
  bind:selected_run_config_id
  {project_id}
  {current_task}
  {pending_run_config_id}
  requires_structured_output={false}
/>
