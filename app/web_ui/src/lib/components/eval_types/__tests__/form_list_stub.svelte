<script lang="ts">
  export let content: unknown[] = []
  export let content_label: string = ""
  export let empty_content: unknown = {}
</script>

<div data-testid="form-list-stub" data-label={content_label}>
  {#each content as _, item_index}
    <slot {item_index} />
  {/each}
</div>
