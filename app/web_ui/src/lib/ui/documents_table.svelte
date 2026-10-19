<script lang="ts">
  // Presentational document table shared by the Document Library page and the
  // "Select from Document Library" picker. It renders rows and emits events —
  // it owns no sort/pagination/URL state. Each parent passes the (already
  // filtered/sorted/paged) documents and decides what the events mean.
  import { createEventDispatcher } from "svelte"
  import type { KilnDocument } from "$lib/types"
  import FileIcon from "$lib/ui/icons/file_icon.svelte"
  import CheckmarkIcon from "$lib/ui/icons/checkmark_icon.svelte"
  import {
    formatDate,
    formatSize,
    mime_type_to_string,
  } from "$lib/utils/formatters"

  export let documents: KilnDocument[] = []
  // Leading checkbox column. Selection state lives in the parent.
  export let selectable: boolean = false
  export let selected_ids: Set<string> = new Set()
  export let select_all_state: "all" | "some" | "none" = "none"
  // Sortable headers. The parent owns the sort state and reacts to `sort`.
  export let sortable: boolean = false
  export let sort_column: string = ""
  export let sort_direction: "asc" | "desc" = "desc"
  // Optional trailing column showing per-document extraction status.
  // doc id -> true (extracted) / false (none yet) / undefined (still checking).
  export let show_extraction: boolean = false
  export let extraction_status: Record<string, boolean | undefined> = {}
  // Which of the standard columns to render. Defaults to all; tighter contexts
  // (e.g. the picker modal) can drop columns that don't aid the decision.
  export let visible_columns: string[] = [
    "kind",
    "friendly_name",
    "original_file.size",
    "created_at",
  ]

  const columns: { key: string; label: string }[] = [
    { key: "kind", label: "Type" },
    { key: "friendly_name", label: "Name" },
    { key: "original_file.size", label: "Size" },
    { key: "created_at", label: "Created At" },
  ]

  const dispatch = createEventDispatcher<{
    sort: { key: string }
    selectAll: { event: Event }
    rowClick: { id: string | null; event: MouseEvent }
  }>()
</script>

<div class="overflow-x-auto rounded-lg border">
  <table class="table">
    <thead>
      <tr>
        {#if selectable}
          <th>
            {#key select_all_state}
              <input
                type="checkbox"
                class="checkbox checkbox-sm mt-1"
                checked={select_all_state === "all"}
                indeterminate={select_all_state === "some"}
                on:change={(event) => dispatch("selectAll", { event })}
              />
            {/key}
          </th>
        {/if}
        {#each columns.filter( (c) => visible_columns.includes(c.key), ) as { key, label }}
          {#if sortable}
            <th
              on:click={() => dispatch("sort", { key })}
              class="hover:bg-base-200 cursor-pointer"
            >
              {label}
              {sort_column === key
                ? sort_direction === "asc"
                  ? "▲"
                  : "▼"
                : ""}
            </th>
          {:else}
            <th>{label}</th>
          {/if}
        {/each}
        {#if show_extraction}
          <th style="width: 110px" class="text-center">Extraction</th>
        {/if}
      </tr>
    </thead>
    <tbody>
      {#each documents as document}
        {@const id = document.id || ""}
        <tr
          class="{selectable ? '' : 'hover'} cursor-pointer {selectable &&
          id &&
          selected_ids.has(id)
            ? 'bg-base-200'
            : ''}"
          on:click={(event) =>
            dispatch("rowClick", { id: document.id || null, event })}
        >
          {#if selectable}
            <td class="w-12">
              <input
                type="checkbox"
                class="checkbox checkbox-sm"
                checked={(id && selected_ids.has(id)) || false}
              />
            </td>
          {/if}
          {#if visible_columns.includes("kind")}
            <td>
              <div class="flex flex-row items-center gap-2">
                <div class="h-8 w-8">
                  <FileIcon kind={document.kind} />
                </div>
                <span class="text-sm">
                  {mime_type_to_string(document.original_file.mime_type)}
                </span>
              </div>
            </td>
          {/if}
          {#if visible_columns.includes("friendly_name")}
            <td>{document.friendly_name}</td>
          {/if}
          {#if visible_columns.includes("original_file.size")}
            <td>{formatSize(document.original_file.size)}</td>
          {/if}
          {#if visible_columns.includes("created_at")}
            <td>{formatDate(document.created_at)}</td>
          {/if}
          {#if show_extraction}
            <td class="text-center">
              {#if extraction_status[id] === undefined}
                <span class="loading loading-spinner loading-xs opacity-50"
                ></span>
              {:else if extraction_status[id]}
                <span
                  class="inline-block w-4 h-4 text-success align-middle"
                  title="Extracted"
                >
                  <CheckmarkIcon />
                </span>
              {:else}
                <span class="text-gray-400" title="No extraction yet">—</span>
              {/if}
            </td>
          {/if}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
