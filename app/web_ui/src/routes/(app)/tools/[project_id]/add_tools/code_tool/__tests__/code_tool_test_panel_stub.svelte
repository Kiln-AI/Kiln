<script lang="ts">
  export let project_id: string = ""
  export let tool_function_name: string = ""
  export let tool_description: string = ""
  export let parameters_schema: unknown = {}
  export let code: string = ""
  export let timeout_seconds: number = 60
  export let tool_allowlist: string[] = []
  // Force "already tested" so the create flow skips the confirm-without-test
  // dialog and goes straight to the create POST (the path under test).
  export let has_tested: boolean = false
  $: has_tested = true
</script>

<div
  data-testid="test-panel-stub"
  data-tool={tool_function_name}
  data-project={project_id}
  data-desc={tool_description}
  data-timeout={timeout_seconds}
  data-code={code}
  data-schema={JSON.stringify(parameters_schema)}
  data-allowlist={tool_allowlist.join(",")}
></div>
