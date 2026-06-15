<script lang="ts">
  import Dialog from "./dialog.svelte"

  export let items: string | string[]
  export let links: (string | null)[] | undefined = undefined
  // When true and there is more than one item, only the first badge is shown
  // inline alongside a "+N more" badge that opens a modal with the full list.
  // Keeps long lists (e.g. tools/skills) from overflowing in tight spaces.
  export let collapse: boolean = false
  // Title shown on the "+N more" modal.
  export let modal_title: string = ""

  let dialog: Dialog

  $: all_items = Array.isArray(items) ? items : []
  $: should_collapse = collapse && all_items.length > 1
  $: visible_items = should_collapse ? all_items.slice(0, 1) : all_items
</script>

{#if Array.isArray(items)}
  <div class="flex flex-wrap gap-1 items-center">
    {#each visible_items as name, i}
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
    {#if should_collapse}
      <button
        class="badge badge-outline hover:bg-base-200"
        on:click|stopPropagation={() => dialog?.show()}
      >
        +{all_items.length - 1} more
      </button>
    {/if}
  </div>

  {#if should_collapse}
    <div
      on:click|stopPropagation
      on:keydown|stopPropagation
      role="presentation"
    >
      <Dialog
        bind:this={dialog}
        title={modal_title}
        width="wide"
        action_buttons={[{ label: "Close", isCancel: true }]}
      >
        <div class="flex flex-wrap gap-1 text-sm text-gray-500">
          {#each all_items as name, i}
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
      </Dialog>
    </div>
  {/if}
{:else}
  {items}
{/if}
