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
  // Top: tag pills ("All" + each tag with count) — multi-select union, "All"
  // mutually exclusive with individual tags. Below: a table of the resolved
  // union where individual items can be unchecked (excluded).
  // Final selection = (union of selected tags) − (manually excluded).
  import { formatDate } from "$lib/utils/formatters"
  import Dialog from "$lib/ui/dialog.svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"

  export let items: TagFirstItem[] = []
  // Header label for the text column in the expanded list.
  export let text_header: string = "Input"
  // Small print under the panel (e.g. the synthetic-exclusion note).
  export let footer_note: string = ""
  // Bound out: the final resolved set of selected item ids.
  export let selected_ids: string[] = []
  // Optional per-row "View in …" action (opens in a new tab). When both are
  // provided, each row gets a ⋯ menu linking to view_href(id).
  export let view_label: string = ""
  export let view_href: ((id: string) => string) | null = null

  $: show_actions = !!view_href && !!view_label

  // Nothing selected by default — the user picks a tag (or All) to begin.
  let all_selected = false
  let selected_tags: Set<string> = new Set()
  let excluded_ids: Set<string> = new Set()

  const PAGE_SIZE = 5
  let current_page = 0

  export function reset() {
    all_selected = false
    selected_tags = new Set()
    excluded_ids = new Set()
    current_page = 0
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

  // Items matching the current tag selection (the union, before exclusions).
  $: union_items = all_selected
    ? items
    : selected_tags.size === 0
      ? []
      : items.filter((it) => it.tags.some((t) => selected_tags.has(t)))

  $: selected_ids = union_items
    .filter((it) => !excluded_ids.has(it.id))
    .map((it) => it.id)

  // Pagination over the union (mirrors the task run picker). Page is reset on
  // tag changes; excluding individual items doesn't change the union length.
  $: total_pages = Math.ceil(union_items.length / PAGE_SIZE)
  $: page_start = current_page * PAGE_SIZE
  $: page_end = Math.min(page_start + PAGE_SIZE, union_items.length)
  $: paged_items = union_items.slice(page_start, page_end)

  function select_all() {
    // Toggle: a second click on All deselects everything.
    all_selected = !all_selected
    selected_tags = new Set()
    current_page = 0
  }

  function toggle_tag(tag: string) {
    all_selected = false
    const next = new Set(selected_tags)
    if (next.has(tag)) next.delete(tag)
    else next.add(tag)
    selected_tags = next
    current_page = 0
  }

  function toggle_exclude(id: string) {
    const next = new Set(excluded_ids)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    excluded_ids = next
  }

  // Empty the selection entirely. Since selection is tag-driven, this clears
  // the tag/All pills too (not just manual exclusions).
  function clear_selection() {
    all_selected = false
    selected_tags = new Set()
    excluded_ids = new Set()
    current_page = 0
  }

  // Tags cell display: first tag + "+N other(s)", matching the dataset table.
  function tag_display(tags: string[]): { first: string; others: number } {
    if (tags.length === 0) return { first: "", others: 0 }
    const sorted = [...tags].sort()
    return { first: sorted[0], others: sorted.length - 1 }
  }

  // View-all-tags dialog (same pattern as the dataset table).
  let tags_dialog: Dialog | null = null
  let dialog_tags: string[] = []
  function show_tags_dialog(tags: string[], event: Event) {
    event.stopPropagation()
    dialog_tags = [...tags].sort()
    tags_dialog?.show()
  }
</script>

<div class="flex flex-col gap-4">
  <div>
    <div class="flex items-center justify-between mb-2 min-h-[20px]">
      <div
        class="text-xs uppercase tracking-wider font-semibold text-[#8a8a8a]"
      >
        Tags
      </div>
      {#if selected_ids.length > 0}
        <button
          type="button"
          class="link text-sm text-gray-500 hover:text-gray-700"
          on:click={clear_selection}
        >
          Clear selection
        </button>
      {/if}
    </div>
    <div class="flex flex-wrap gap-2">
      <button
        type="button"
        class="badge py-3 px-3 gap-1 border {all_selected
          ? 'bg-primary/10 text-primary border-primary'
          : 'bg-gray-200 text-gray-500 border-transparent hover:bg-gray-300'}"
        on:click={select_all}
      >
        {#if all_selected}✓{/if}
        <span>All</span>
        <span class="font-normal opacity-70 tabular-nums">({items.length})</span
        >
      </button>
      {#each tag_counts as [tag, count]}
        {@const active = !all_selected && selected_tags.has(tag)}
        <button
          type="button"
          class="badge py-3 px-3 gap-1 border max-w-full {active
            ? 'bg-primary/10 text-primary border-primary'
            : 'bg-gray-200 text-gray-500 border-transparent hover:bg-gray-300'}"
          on:click={() => toggle_tag(tag)}
        >
          {#if active}✓{/if}
          <span class="truncate">{tag}</span>
          <span class="font-normal opacity-70 tabular-nums">({count})</span>
        </button>
      {/each}
    </div>
  </div>

  {#if union_items.length > 0}
    <div>
      <div class="overflow-hidden rounded-lg border border-base-300 bg-white">
        <table class="table tff-table">
          <thead>
            <tr>
              <th class="w-px"></th>
              <th>{text_header}</th>
              <th>Tags</th>
              <th class="whitespace-nowrap">Created</th>
              {#if show_actions}
                <th class="w-px"></th>
              {/if}
            </tr>
          </thead>
          <tbody>
            {#each paged_items as it (it.id)}
              {@const td = tag_display(it.tags)}
              <tr
                class="cursor-pointer hover:bg-base-200"
                on:click={() => toggle_exclude(it.id)}
              >
                <td class="py-2 align-top">
                  <input
                    type="checkbox"
                    class="checkbox checkbox-sm"
                    checked={!excluded_ids.has(it.id)}
                    on:click|stopPropagation
                    on:change={() => toggle_exclude(it.id)}
                  />
                </td>
                <td class="py-2 align-top">
                  <div
                    class="line-clamp-2 break-words text-[13px] text-gray-800"
                  >
                    {it.text}
                  </div>
                </td>
                <td class="py-2 align-top">
                  {#if td.first}
                    <button
                      type="button"
                      class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full cursor-pointer hover:bg-gray-300"
                      on:click|stopPropagation={(e) =>
                        show_tags_dialog(it.tags, e)}
                    >
                      <span class="truncate">{td.first}</span>
                      {#if td.others > 0}
                        <span class="ml-1 font-medium text-nowrap">
                          +{td.others}
                          {td.others === 1 ? "other" : "others"}
                        </span>
                      {/if}
                    </button>
                  {/if}
                </td>
                <td
                  class="py-2 align-top text-xs text-gray-500 whitespace-nowrap"
                >
                  {formatDate(it.date ?? undefined)}
                </td>
                {#if show_actions && view_href}
                  <td class="py-2 align-top" on:click|stopPropagation>
                    <TableActionMenu
                      items={[
                        {
                          label: view_label,
                          href: view_href(it.id),
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
      {#if union_items.length > PAGE_SIZE}
        <div
          class="flex items-center justify-center gap-2 text-xs text-gray-500 mt-2"
        >
          <span>{page_start + 1}-{page_end} of {union_items.length}</span>
          <div class="flex gap-1">
            <button
              type="button"
              class="btn btn-xs btn-ghost"
              disabled={current_page === 0}
              on:click={() => (current_page = current_page - 1)}
            >
              Prev
            </button>
            <button
              type="button"
              class="btn btn-xs btn-ghost"
              disabled={current_page >= total_pages - 1}
              on:click={() => (current_page = current_page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      {/if}
    </div>
  {/if}

  {#if footer_note}
    <div class="text-[12.5px] text-[#9a9a9a]">{footer_note}</div>
  {/if}
</div>

<Dialog
  bind:this={tags_dialog}
  title="Tags"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  <div class="flex flex-row flex-wrap gap-2">
    {#each dialog_tags as tag}
      <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
        <span class="truncate">{tag}</span>
      </div>
    {/each}
  </div>
</Dialog>

<style>
  /* Tighter cell padding than daisy's default px-4 so the fixed columns fit
     the dialog width without a horizontal scrollbar. */
  .tff-table :global(th),
  .tff-table :global(td) {
    padding-left: 0.625rem;
    padding-right: 0.625rem;
  }
</style>
