<script lang="ts">
  // Stands in for the heavy editor, tools selector and test panel the code step
  // renders. Props are declared only to keep Svelte from warning about them.
  export let value: string = ""
  export let min_height: string = ""
  export let project_id: string = ""
  export let label: string = ""
  export let settings: Record<string, unknown> | undefined = undefined
  export let tools: string[] = []
  export let code: string = ""
  export let tool_function_name: string = ""
  export let tool_description: string = ""
  export let parameters_schema: Record<string, unknown> | undefined = undefined
  export let timeout_seconds: number = 0
  export let tool_allowlist: string[] = []
  export let has_tested: boolean = false
  $: void [
    value,
    min_height,
    project_id,
    label,
    settings,
    tools,
    code,
    tool_function_name,
    tool_description,
    parameters_schema,
    timeout_seconds,
    tool_allowlist,
    has_tested,
  ]

  export function setValue(_: string) {}
</script>

<div data-testid="passthrough-stub"><slot /></div>
