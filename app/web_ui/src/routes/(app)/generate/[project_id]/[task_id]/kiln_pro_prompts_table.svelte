<script lang="ts">
  import TrashIcon from "$lib/ui/icons/trash_icon.svelte"

  export let prompts: string[]
  // When provided, each row gets a delete action.
  export let on_delete: ((index: number) => void) | null = null

  let show_prompts = false

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
    on:click={() => (show_prompts = !show_prompts)}
  >
    <div class="flex items-center gap-2 text-sm">
      <span class="font-medium">The plan</span>
      <span class="text-gray-400">·</span>
      <span class="font-medium">{count}</span>
      <span class="text-gray-500">prompts</span>
    </div>
    <div class="flex items-center gap-1 text-sm text-gray-500">
      {show_prompts ? "Hide prompts" : "Show prompts"}
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
          <th>Prompt</th>
          <th class="w-28">Status</th>
          {#if on_delete}
            <th class="w-12"></th>
          {/if}
        </tr>
      </thead>
      <tbody>
        {#each visible as prompt, i}
          <tr>
            <td class="text-gray-500">{pad(start + i + 1)}</td>
            <td class="whitespace-normal">{prompt}</td>
            <td>
              <span
                class="inline-flex items-center gap-1.5 text-xs text-gray-500"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-gray-400"></span>
                Planned
              </span>
            </td>
            {#if on_delete}
              <td>
                <button
                  class="btn btn-ghost btn-xs text-gray-400 hover:text-error"
                  aria-label="Delete prompt"
                  on:click={() => on_delete?.(start + i)}
                >
                  <span class="w-4 h-4"><TrashIcon /></span>
                </button>
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
