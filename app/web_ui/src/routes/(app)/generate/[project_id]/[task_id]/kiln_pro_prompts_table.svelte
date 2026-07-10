<script lang="ts">
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"

  export let prompts: string[]
  // When provided, each row gets a delete action.
  export let on_delete: ((index: number) => void) | null = null

  let show_prompts = false
</script>

<div class="rounded-lg border">
  <button
    class="w-full flex items-center justify-between px-4 py-3 text-left"
    on:click={() => (show_prompts = !show_prompts)}
  >
    <span class="text-sm font-medium">Batch Prompts</span>
    <div class="flex items-center gap-1 text-sm text-gray-500">
      {show_prompts ? "Hide" : "Show"}
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
      <tbody>
        {#each prompts as prompt, i}
          <tr>
            <td class="whitespace-normal">{prompt}</td>
            {#if on_delete}
              <td class="w-12 align-top">
                <div class="flex flex-row justify-end items-start">
                  <TableActionMenu
                    width="w-40"
                    items={[
                      {
                        label: "Delete",
                        onclick: () => on_delete?.(i),
                      },
                    ]}
                  />
                </div>
              </td>
            {/if}
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
