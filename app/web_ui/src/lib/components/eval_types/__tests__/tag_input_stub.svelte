<script lang="ts">
  export let tags: string[] = []
  export let placeholder: string = ""
  export let disabled: boolean = false
  export let id: string = ""
</script>

<div data-testid="tag-input-{id}" data-disabled={disabled}>
  {#each tags as tag}
    <span>{tag}</span>
  {/each}
</div>
