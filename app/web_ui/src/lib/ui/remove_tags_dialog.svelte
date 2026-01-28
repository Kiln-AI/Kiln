<script lang="ts">
  import Dialog from "./dialog.svelte"

  export let title: string
  export let remove_tags: Set<string> = new Set()
  export let available_tags: Record<string, number> = {}
  export let onRemoveTag: (tag: string) => void = () => {}
  export let onAddTagToRemove: (tag: string) => void = () => {}
  export let onRemoveTags: () => Promise<boolean> = async () => true

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
  }

  export function close() {
    dialog?.close()
  }
</script>

<Dialog
  bind:this={dialog}
  {title}
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Remove Tags",
      asyncAction: onRemoveTags,
      disabled: remove_tags.size == 0,
      isError: true,
    },
  ]}
>
  <div>
    <div class="text-sm font-light text-gray-500 mt-6">
      Selected tags to remove:
    </div>
    {#if remove_tags.size == 0}
      <div class="text-xs font-medium">No tags selected.</div>
    {:else}
      <div class="flex flex-row flex-wrap gap-2 mt-2">
        {#each Array.from(remove_tags).sort() as tag}
          <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
            <span class="truncate">{tag}</span>
            <button
              class="pl-3 font-medium shrink-0"
              on:click={() => onRemoveTag(tag)}>✕</button
            >
          </div>
        {/each}
      </div>
    {/if}
    <div class="text-sm font-light text-gray-500 mt-6">Available tags:</div>
    {#if Object.keys(available_tags).length == 0 && remove_tags.size == 0}
      <div class="text-xs font-medium">No tags on selected items.</div>
    {:else if Object.keys(available_tags).length == 0}
      <div class="text-xs font-medium">
        All available tags already selected.
      </div>
    {:else}
      <div class="flex flex-row flex-wrap gap-2 mt-2">
        {#each Object.entries(available_tags).sort((a, b) => b[1] - a[1]) as [tag, count]}
          {#if !remove_tags.has(tag)}
            <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
              <button class="truncate" on:click={() => onAddTagToRemove(tag)}>
                {tag} ({count})
              </button>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  </div>
</Dialog>
