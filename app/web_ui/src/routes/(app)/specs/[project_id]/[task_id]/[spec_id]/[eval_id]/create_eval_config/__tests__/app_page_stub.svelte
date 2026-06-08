<script lang="ts">
  export let title: string = ""
  export let subtitle: string = ""
  export let sub_subtitle: string = ""
  export let sub_subtitle_link: string | undefined = undefined
  export let breadcrumbs: Array<Record<string, unknown>> = []
</script>

<div data-testid="app-page-stub" data-title={title}>
  <slot />
</div>
