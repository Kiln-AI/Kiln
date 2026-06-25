<script lang="ts">
  import type { EvalTypeTag } from "$lib/utils/eval_types/registry"

  export let tags: EvalTypeTag[]
</script>

<div class="flex flex-wrap gap-1.5">
  {#each tags as tag}
    <span
      class="badge badge-sm badge-outline {tag.tone === 'beta'
        ? 'badge-primary'
        : ''}"
    >
      {tag.label}
    </span>
  {/each}
</div>
