<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import ManualExampleDialog from "./manual_example_dialog.svelte"
  import type { TaskRunOutput } from "$lib/types"

  export let available_runs: TaskRunOutput[] = []

  let dialog: Dialog
  let manual_dialog: ManualExampleDialog

  const PAGE_SIZE = 5
  let current_page = 0
  $: total_pages = Math.ceil(available_runs.length / PAGE_SIZE)
  $: page_start = current_page * PAGE_SIZE
  $: page_end = Math.min(page_start + PAGE_SIZE, available_runs.length)
  $: paged_runs = available_runs.slice(page_start, page_end)

  const dispatch = createEventDispatcher<{
    select: TaskRunOutput
  }>()

  export function show() {
    current_page = 0
    dialog?.show()
  }

  function format_date(date_str: string | undefined | null): string {
    if (!date_str) return ""
    const date = new Date(date_str)
    if (isNaN(date.getTime())) return ""
    const now = new Date()
    const diff_ms = now.getTime() - date.getTime()
    const diff_hours = Math.floor(diff_ms / (1000 * 60 * 60))
    if (diff_hours < 1) return "just now"
    if (diff_hours < 24) return `${diff_hours}h ago`
    const diff_days = Math.floor(diff_hours / 24)
    if (diff_days === 1) return "yesterday"
    return `${diff_days}d ago`
  }

  function truncate(text: string, max_length: number = 80): string {
    if (text.length <= max_length) return text
    return text.substring(0, max_length) + "..."
  }

  function select_run(run: TaskRunOutput) {
    dispatch("select", run)
    dialog?.close()
  }

  function handle_manual_confirm(e: CustomEvent<TaskRunOutput>) {
    dispatch("select", e.detail)
    dialog?.close()
  }
</script>

<Dialog
  bind:this={dialog}
  title="Choose Dataset Sample"
  subtitle="Pick a dataset item to test this scorer against."
  width="wide"
>
  <div class="flex flex-col gap-4">
    <div class="overflow-x-auto">
      <table class="table table-fixed w-full" data-testid="browse-table">
        <thead>
          <tr class="bg-base-200 text-xs uppercase text-gray-500">
            <th>Input preview</th>
            <th>Output preview</th>
            <th class="w-28">Created</th>
          </tr>
        </thead>
        <tbody>
          {#each paged_runs as run}
            <tr
              class="cursor-pointer hover:bg-base-200/50"
              on:click={() => select_run(run)}
            >
              <td class="py-2">
                <span
                  class="text-xs text-gray-500 font-mono"
                  title={run.input ?? ""}
                >
                  {truncate(run.input ?? "")}
                </span>
              </td>
              <td class="py-2">
                <span
                  class="text-xs text-gray-500 font-mono"
                  title={run.output?.output ?? ""}
                >
                  {truncate(run.output?.output ?? "")}
                </span>
              </td>
              <td class="py-2 text-xs text-gray-500">
                {format_date(run.created_at)}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if total_pages > 1}
      <div class="flex items-center justify-center gap-2 text-xs text-gray-500">
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

    <div class="flex items-center justify-end border-t border-base-200 pt-3">
      <button
        type="button"
        class="btn btn-sm btn-ghost text-primary font-bold"
        on:click={() => manual_dialog?.show()}
        data-testid="add-manual-example"
      >
        <i class="bi bi-plus-circle"></i>
        or add manual example
      </button>
    </div>
  </div>
</Dialog>

<ManualExampleDialog
  bind:this={manual_dialog}
  on:confirm={handle_manual_confirm}
/>
