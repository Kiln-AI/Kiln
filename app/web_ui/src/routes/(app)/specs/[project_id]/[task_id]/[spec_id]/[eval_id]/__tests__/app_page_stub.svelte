<script lang="ts">
  export let title: string = ""
  export let subtitle: string = ""
  export let sub_subtitle: string = ""
  export let sub_subtitle_link: string | undefined = undefined
  export let breadcrumbs: Array<Record<string, unknown>> = []
  export let action_buttons: Array<Record<string, unknown>> = []
</script>

<div
  data-testid="app-page-stub"
  data-title={title}
  data-subtitle={subtitle}
  data-sub-subtitle={sub_subtitle || undefined}
  data-sub-subtitle-link={sub_subtitle_link || undefined}
>
  {#if sub_subtitle}
    <span data-testid="sub-subtitle-text">{sub_subtitle}</span>
  {/if}
  <slot />
</div>
