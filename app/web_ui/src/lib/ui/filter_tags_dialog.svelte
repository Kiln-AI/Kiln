<script lang="ts">
  import Dialog from "./dialog.svelte"

  export let title: string
  export let filter_tags: string[] = []
  export let available_filter_tags: Record<string, number> = {}
  export let onRemoveFilterTag: (tag: string) => void = () => {}
  export let onAddFilterTag: (tag: string) => void = () => {}

  let dialog: Dialog | null = null
  let search_text = ""
  let search_input: HTMLInputElement | null = null

  export function show() {
    dialog?.show()
  }

  export function close() {
    dialog?.close()
  }

  function on_dialog_show() {
    // Reset the search each time the dialog opens, then focus the input so
    // users can just start typing to search for a tag.
    search_text = ""
    setTimeout(() => search_input?.focus(), 0)
  }

  $: sorted_available_tags = Object.entries(available_filter_tags).sort(
    (a, b) => b[1] - a[1],
  )

  $: filtered_available_tags = (() => {
    const query = search_text.trim().toLowerCase()
    if (!query) {
      return sorted_available_tags
    }
    return sorted_available_tags.filter(([tag]) =>
      tag.toLowerCase().includes(query),
    )
  })()
</script>

<Dialog
  bind:this={dialog}
  {title}
  action_buttons={[{ label: "Close", isCancel: true }]}
  on:show={on_dialog_show}
>
  {#if filter_tags.length > 0}
    <div class="text-sm mb-2 font-medium">Current Filters:</div>
  {/if}
  <div class="flex flex-row gap-2 flex-wrap">
    {#each filter_tags as tag}
      <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
        <span class="truncate">{tag}</span>
        <button
          class="pl-3 font-medium shrink-0"
          on:click={() => onRemoveFilterTag(tag)}>✕</button
        >
      </div>
    {/each}
  </div>

  <div class="text-sm mt-4 mb-2 font-medium">Add a filter:</div>
  {#if Object.keys(available_filter_tags).length == 0}
    <p class="text-sm text-gray-500">
      Any further filters would show zero results.
    </p>
  {:else}
    <input
      bind:this={search_input}
      bind:value={search_text}
      type="text"
      autocomplete="off"
      autocapitalize="none"
      spellcheck="false"
      placeholder="Search tags…"
      class="input input-bordered input-sm w-full mb-3"
    />
    <div class="flex flex-row gap-2 flex-wrap">
      {#each filtered_available_tags as [tag, count]}
        <button
          class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full"
          on:click={() => onAddFilterTag(tag)}>{tag} ({count})</button
        >
      {/each}
    </div>
    {#if filtered_available_tags.length === 0}
      <p class="text-sm text-gray-500">No tags match "{search_text}".</p>
    {/if}
  {/if}
</Dialog>
