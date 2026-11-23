<script lang="ts">
  // Binds selected_run_config_id, model, tools and skills so a test can read
  // what the component writes back, and can set a picker's value from outside.
  // with_saved_configs_dropdown adds the dropdown the Run page puts above the
  // component, bound to the same selection, for tests of the last-used value.
  import type { Task } from "$lib/types"
  import RunConfigComponent from "../run_config_component.svelte"
  import SavedRunConfigsDropdown from "../saved_run_configs_dropdown.svelte"

  export let project_id: string
  export let current_task: Task
  export let selected_run_config_id: string | null = null
  export let model: string | null = null
  export let tools: string[] = []
  export let skills: string[] = []
  export let with_saved_configs_dropdown: boolean = false
</script>

{#if with_saved_configs_dropdown}
  <SavedRunConfigsDropdown
    {project_id}
    {current_task}
    bind:selected_run_config_id
  />
{/if}
<RunConfigComponent
  {project_id}
  {current_task}
  bind:selected_run_config_id
  bind:model
  bind:tools
  bind:skills
  show_name_field={false}
  hide_prompt_selector={true}
/>
<div data-testid="selected_run_config_id">{selected_run_config_id}</div>
<div data-testid="tools">{JSON.stringify(tools)}</div>
<div data-testid="skills">{JSON.stringify(skills)}</div>
