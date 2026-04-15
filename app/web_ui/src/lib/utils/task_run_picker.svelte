<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { TaskRun } from "$lib/types"

  export let available_runs: TaskRun[] = []

  const PAGE_SIZE = 5
  let current_page = 0
  $: total_pages = Math.ceil(available_runs.length / PAGE_SIZE)
  $: page_start = current_page * PAGE_SIZE
  $: page_end = Math.min(page_start + PAGE_SIZE, available_runs.length)
  $: paged_runs = available_runs.slice(page_start, page_end)

  let expanded: boolean[] = []
  let prev_len = 0
  $: if (paged_runs.length !== prev_len) {
    prev_len = paged_runs.length
    expanded = new Array(paged_runs.length).fill(false)
  }

  function toggle_expand(index: number) {
    expanded[index] = !expanded[index]
    expanded = expanded
  }

  const dispatch = createEventDispatcher<{
    select: TaskRun
  }>()
</script>

{#if available_runs.length > 0}
  <div class="overflow-x-auto rounded-lg border bg-white">
    <table class="table table-fixed">
      <thead>
        <tr>
          <th>Input</th>
          <th>Output</th>
          <th style="width: 80px"></th>
        </tr>
      </thead>
      <tbody>
        {#each paged_runs as run, i}
          <tr
            on:click={() => toggle_expand(i)}
            class="cursor-pointer hover:bg-base-200"
          >
            <td class="py-2">
              {#if expanded[i]}
                <pre
                  class="whitespace-pre-wrap break-words text-xs text-gray-600">{run.input ?? ""}</pre>
              {:else}
                <div class="truncate text-xs text-gray-600">
                  {run.input ?? ""}
                </div>
              {/if}
            </td>
            <td class="py-2">
              {#if expanded[i]}
                <pre
                  class="whitespace-pre-wrap break-words text-xs text-gray-600">{run.output?.output ?? ""}</pre>
              {:else}
                <div class="truncate text-xs text-gray-600">
                  {run.output?.output ?? ""}
                </div>
              {/if}
            </td>
            <td class="py-2 text-center">
              <button
                type="button"
                class="btn btn-xs btn-outline"
                on:click|stopPropagation={() => dispatch("select", run)}
              >
                Select
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if available_runs.length > PAGE_SIZE}
    <div
      class="flex items-center justify-center gap-2 text-xs text-gray-500 mt-2"
    >
      <span>{page_start + 1}-{page_end} of {available_runs.length}</span>
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
{:else}
  <div class="text-sm text-gray-400">No existing data available.</div>
{/if}
