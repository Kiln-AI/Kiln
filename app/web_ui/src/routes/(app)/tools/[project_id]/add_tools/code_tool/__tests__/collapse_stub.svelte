<script lang="ts">
  export let title: string = ""
</script>

<div data-testid="collapse-stub" data-title={title}>
  <slot />
</div>
