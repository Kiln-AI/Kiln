<script lang="ts">
  export let title: string = ""
  export let subtitle: string = ""
  export let breadcrumbs: Array<Record<string, unknown>> = []
</script>

<div
  data-testid="app-page-stub"
  data-title={title}
  data-subtitle={subtitle}
  data-breadcrumbs={JSON.stringify(breadcrumbs)}
>
  <slot />
</div>
