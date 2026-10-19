<script lang="ts">
  export let title: string = ""
  export let description: string | null = null
  export let open: boolean = false
</script>

<div data-testid="collapse-stub" data-title={title} data-open={open}>
  <slot />
</div>
