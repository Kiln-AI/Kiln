<script lang="ts">
  export let title: string = ""
  export let subtitle: string = ""
  export let breadcrumbs: unknown = null
</script>

<div data-testid="app-page-stub" data-title={title} data-subtitle={subtitle}>
  {breadcrumbs ? "" : ""}
  <slot />
</div>
