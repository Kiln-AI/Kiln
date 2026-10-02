<script lang="ts">
  export let tools: string[] = []
  export let project_id: string = ""
  export let label: string = ""
  export let settings: unknown = {}
</script>

<div
  data-testid="tools-selector-stub"
  data-project={project_id}
  data-label={label}
  data-settings={settings ? "set" : ""}
  data-tools={tools.join(",")}
></div>
