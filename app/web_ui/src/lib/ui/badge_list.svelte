<script lang="ts">
  export let items: string | string[]
  export let links: (string | null)[] | undefined = undefined
</script>

{#if Array.isArray(items)}
  <div class="flex flex-wrap gap-1">
    {#each items as name, i}
      {@const link = links?.[i]}
      {#if link}
        <a
          href={link}
          class="badge badge-outline hover:bg-base-200"
          on:click|stopPropagation
        >
          {name}
        </a>
      {:else}
        <span class="badge badge-outline">{name}</span>
      {/if}
    {/each}
  </div>
{:else}
  {items}
{/if}
