<script lang="ts">
  // Binds selected_run_config_id, tools and skills so a test can read what the
  // component writes back, and can set a picker's value from outside.
  import type { Task } from "$lib/types"
  import RunConfigComponent from "../run_config_component.svelte"

  export let project_id: string
  export let current_task: Task
  export let selected_run_config_id: string | null = null
  export let tools: string[] = []
  export let skills: string[] = []
</script>

<RunConfigComponent
  {project_id}
  {current_task}
  bind:selected_run_config_id
  bind:tools
  bind:skills
  show_name_field={false}
  hide_prompt_selector={true}
/>
<div data-testid="selected_run_config_id">{selected_run_config_id}</div>
<div data-testid="tools">{JSON.stringify(tools)}</div>
<div data-testid="skills">{JSON.stringify(skills)}</div>
