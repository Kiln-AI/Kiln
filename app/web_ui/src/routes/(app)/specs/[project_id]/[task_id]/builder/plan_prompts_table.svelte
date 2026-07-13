<script lang="ts" context="module">
  // Per-row Status pill. `tone` maps to a dot colour; `title` surfaces
  // detail (e.g. a failure message) on hover.
  export type RowStatusPill = {
    label: string
    tone: "pending" | "active" | "done" | "error"
    title?: string | null
  }
</script>

<script lang="ts">
  import TrashIcon from "$lib/ui/icons/trash_icon.svelte"
  import EditIcon from "$lib/ui/icons/edit_icon.svelte"

  // Builder-local plan table: the approval step needs inline edit, live
  // per-row status, and pagination, which /generate's simpler
  // kiln_pro_prompts_table deliberately doesn't carry.
  export let prompts: string[]
  // When provided, each row gets a delete action.
  export let on_delete: ((index: number) => void) | null = null
  // When provided, each row gets an edit action (opens the edit dialog).
  export let on_edit: ((index: number, value: string) => void) | null = null
  // Open the prompt list on mount — for flows where reviewing the prompts is
  // the point (e.g. plan approval) rather than an optional peek.
  export let start_expanded = false
  // What each planned row represents, for flows where "prompts" isn't the
  // user-facing noun (the eval builder plans one synthetic user per row).
  export let item_label = "prompts"
  export let item_label_singular = "Prompt"
  // Live per-row status (index-aligned with prompts). When null every row
  // shows the static "Planned" pill.
  export let row_statuses: RowStatusPill[] | null = null

  const status_dot_class: Record<RowStatusPill["tone"], string> = {
    pending: "bg-gray-400",
    active: "bg-primary animate-pulse",
    done: "bg-success",
    error: "bg-error",
  }

  let show_prompts = start_expanded

  // Edit dialog state — mirrors the prompt-popup pattern in
  // kiln_pro_inputs.svelte (dialog + showModal), keeping rows read-only.
  const edit_dialog_id = "builder_plan_prompt_edit_dialog"
  let editing_index: number | null = null
  let editing_value = ""

  function open_edit(index: number) {
    editing_index = index
    editing_value = prompts[index]
    // @ts-expect-error showModal is not typed on HTMLElement
    document.getElementById(edit_dialog_id)?.showModal()
  }

  function save_edit() {
    if (editing_index !== null) {
      const value = editing_value.trim()
      if (value && value !== prompts[editing_index]) {
        on_edit?.(editing_index, value)
      }
    }
    editing_index = null
    // @ts-expect-error close is not typed on HTMLElement
    document.getElementById(edit_dialog_id)?.close()
  }

  const per_page = 10
  let page = 0
  $: count = prompts.length
  $: page_count = Math.max(1, Math.ceil(count / per_page))
  // Clamp the page if the plan shrinks (e.g. after deleting prompts).
  $: if (page > page_count - 1) page = page_count - 1
  $: start = page * per_page
  $: visible = prompts.slice(start, start + per_page)

  function pad(n: number): string {
    return String(n).padStart(2, "0")
  }
</script>

<div class="rounded-lg border">
  <button
    class="w-full flex items-center justify-between px-4 py-3 text-left"
    aria-expanded={show_prompts}
    on:click={() => (show_prompts = !show_prompts)}
  >
    <div class="flex items-center gap-2 text-sm">
      <span class="font-medium">The plan</span>
      <span class="text-gray-400">·</span>
      <span class="font-medium">{count}</span>
      <span class="text-gray-500">{item_label}</span>
    </div>
    <div class="flex items-center gap-1 text-sm text-gray-500">
      {show_prompts ? `Hide ${item_label}` : `Show ${item_label}`}
      <svg
        class="w-4 h-4 transition-transform {show_prompts ? 'rotate-180' : ''}"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
  </button>

  {#if show_prompts}
    <table class="table table-fixed border-t">
      <thead>
        <tr>
          <th class="w-14">#</th>
          <th>{item_label_singular}</th>
          <th class="w-28">Status</th>
          {#if on_edit || on_delete}
            <th class="w-24"></th>
          {/if}
        </tr>
      </thead>
      <tbody>
        {#each visible as prompt, i}
          <tr>
            <td class="text-gray-500 align-top">{pad(start + i + 1)}</td>
            <td class="whitespace-normal align-top">{prompt}</td>
            <td class="align-top">
              {#if row_statuses && row_statuses[start + i]}
                <span
                  class="inline-flex items-center gap-1.5 text-xs text-gray-500"
                  title={row_statuses[start + i].title ?? null}
                >
                  <span
                    class="w-1.5 h-1.5 rounded-full {status_dot_class[
                      row_statuses[start + i].tone
                    ]}"
                  ></span>
                  {row_statuses[start + i].label}
                </span>
              {:else}
                <span
                  class="inline-flex items-center gap-1.5 text-xs text-gray-500"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-gray-400"></span>
                  Planned
                </span>
              {/if}
            </td>
            {#if on_edit || on_delete}
              <td class="align-top">
                <div class="flex gap-1">
                  {#if on_edit}
                    <button
                      class="btn btn-square btn-ghost btn-xs text-gray-400 hover:text-primary"
                      aria-label="Edit {item_label_singular}"
                      on:click={() => open_edit(start + i)}
                    >
                      <span class="w-4 h-4"><EditIcon /></span>
                    </button>
                  {/if}
                  {#if on_delete}
                    <button
                      class="btn btn-square btn-ghost btn-xs text-gray-400 hover:text-error"
                      aria-label="Delete {item_label_singular}"
                      on:click={() => on_delete?.(start + i)}
                    >
                      <span class="w-4 h-4"><TrashIcon /></span>
                    </button>
                  {/if}
                </div>
              </td>
            {/if}
          </tr>
        {/each}
      </tbody>
    </table>

    <div
      class="flex items-center justify-between px-4 py-3 border-t text-sm font-light text-gray-500"
    >
      <div>
        Showing {start + 1}–{Math.min(start + per_page, count)} of {count}
      </div>
      <div class="flex gap-2">
        <button
          class="btn btn-xs"
          disabled={page === 0}
          on:click={() => (page = Math.max(0, page - 1))}
        >
          Prev
        </button>
        <button
          class="btn btn-xs"
          disabled={page >= page_count - 1}
          on:click={() => (page = Math.min(page_count - 1, page + 1))}
        >
          Next
        </button>
      </div>
    </div>
  {/if}
</div>

<!-- Edit prompt dialog -->
<dialog id={edit_dialog_id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold mb-1">
      Edit {item_label_singular}
      {editing_index !== null ? pad(editing_index + 1) : ""}
    </h3>
    <p class="text-sm font-light text-gray-500 mb-4">
      Changes apply to this entry only; the plan summary is not regenerated.
    </p>
    <textarea
      class="textarea textarea-bordered w-full text-sm"
      rows="6"
      bind:value={editing_value}
    ></textarea>
    <div class="flex justify-end mt-4">
      <button
        class="btn btn-sm btn-primary"
        disabled={!editing_value.trim()}
        on:click={save_edit}
      >
        Save
      </button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
