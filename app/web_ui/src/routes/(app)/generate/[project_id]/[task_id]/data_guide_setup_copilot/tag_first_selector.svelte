<script lang="ts" context="module">
  export type TagFirstItem = {
    id: string
    text: string
    tags: string[]
    date?: string | null
  }
</script>

<script lang="ts">
  // Tag-first selection shared by the document-library and dataset pickers.
  // A scrollable table of tags (with per-tag counts); checking tags builds a
  // deduplicated union of the matching items. The union total shows top-right
  // of the table and links out to the source list filtered by those tags.
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"

  export let items: TagFirstItem[] = []
  // Header for the count column and the noun used in the union-total line.
  export let count_header: string = "Samples"
  export let unit_singular: string = "sample"
  export let unit_plural: string = "samples"
  // Bound out: the final resolved set of selected item ids (the tag union).
  export let selected_ids: string[] = []
  // Builds a URL to the source list page filtered by the given tags. When set,
  // the union total becomes a link opening that page in a new tab, and each row
  // gets a ⋯ menu that opens the page filtered to that single tag.
  export let filtered_href: ((tags: string[]) => string) | null = null
  // Label for the per-row action menu item, e.g. "View Runs" / "View Documents".
  export let row_action_label: string = "View"

  let selected_tags: Set<string> = new Set()

  export function reset() {
    selected_tags = new Set()
  }

  // Tag -> count among items, most-common first.
  $: tag_counts = (() => {
    const counts = new Map<string, number>()
    for (const it of items) {
      for (const t of it.tags) counts.set(t, (counts.get(t) || 0) + 1)
    }
    return [...counts.entries()].sort(
      (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
    )
  })()

  // Items matching the current tag selection (deduplicated union).
  $: union_items =
    selected_tags.size === 0
      ? []
      : items.filter((it) => it.tags.some((t) => selected_tags.has(t)))

  $: selected_ids = union_items.map((it) => it.id)

  $: all_checked =
    tag_counts.length > 0 && selected_tags.size === tag_counts.length
  $: some_checked = selected_tags.size > 0 && !all_checked
  $: select_summary = all_checked ? "all" : some_checked ? "some" : "none"

  function toggle_tag(tag: string) {
    const next = new Set(selected_tags)
    if (next.has(tag)) next.delete(tag)
    else next.add(tag)
    selected_tags = next
  }

  function toggle_all() {
    selected_tags = all_checked
      ? new Set()
      : new Set(tag_counts.map(([tag]) => tag))
  }

  $: union_href =
    filtered_href && selected_tags.size > 0
      ? filtered_href([...selected_tags])
      : null
</script>

<div class="flex flex-col gap-2">
  <div
    class="flex min-h-[20px] items-center justify-end gap-1.5 text-sm text-gray-500"
  >
    {#if selected_tags.size > 0}
      <span>
        {selected_tags.size}
        {selected_tags.size === 1 ? "tag" : "tags"}
      </span>
      <span aria-hidden="true">·</span>
      {#if union_href}
        <a
          href={union_href}
          target="_blank"
          rel="noopener noreferrer"
          class="link hover:text-gray-900"
          title="Open the filtered list in a new tab"
        >
          {selected_ids.length}
          {selected_ids.length === 1 ? unit_singular : unit_plural}
        </a>
      {:else}
        <span>
          {selected_ids.length}
          {selected_ids.length === 1 ? unit_singular : unit_plural}
        </span>
      {/if}
    {:else}
      <span>Select tags to add their {unit_plural}</span>
    {/if}
  </div>
  <div class="overflow-hidden rounded-lg border">
    <div class="max-h-[320px] overflow-y-auto">
      <table class="table">
        <thead class="sticky top-0 z-10 bg-base-100">
          <tr>
            <th class="w-px">
              {#key select_summary}
                <input
                  type="checkbox"
                  class="checkbox checkbox-sm"
                  checked={all_checked}
                  indeterminate={some_checked}
                  on:change={toggle_all}
                  aria-label="Select all tags"
                />
              {/key}
            </th>
            <th>Tag</th>
            <th class="text-right">{count_header}</th>
            {#if filtered_href}
              <th class="w-px"></th>
            {/if}
          </tr>
        </thead>
        <tbody>
          {#each tag_counts as [tag, count] (tag)}
            <tr
              class="hover cursor-pointer {selected_tags.has(tag)
                ? 'bg-base-200'
                : ''}"
              on:click={() => toggle_tag(tag)}
            >
              <td>
                <input
                  type="checkbox"
                  class="checkbox checkbox-sm"
                  checked={selected_tags.has(tag)}
                />
              </td>
              <td class="break-all">{tag}</td>
              <td class="text-right tabular-nums">{count}</td>
              {#if filtered_href}
                <td class="w-px" on:click|stopPropagation>
                  <TableActionMenu
                    items={[
                      {
                        label: row_action_label,
                        href: filtered_href([tag]),
                        target: "_blank",
                        rel: "noopener noreferrer",
                      },
                    ]}
                  />
                </td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
</div>
