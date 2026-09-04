<script lang="ts">
  export let project_id: string = ""
  export let on_trust_granted: (() => void) | null = null

  export function show(): void {
    on_trust_granted?.()
  }
</script>

<div data-testid="trust-dialog-stub" data-project={project_id}></div>
