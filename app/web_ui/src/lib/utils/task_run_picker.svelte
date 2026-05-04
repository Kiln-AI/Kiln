<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { TaskRun } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"

  export let available_runs: TaskRun[] = []

  const PAGE_SIZE = 5
  let current_page = 0
  $: total_pages = Math.ceil(available_runs.length / PAGE_SIZE)
  $: page_start = current_page * PAGE_SIZE
  $: page_end = Math.min(page_start + PAGE_SIZE, available_runs.length)
  $: paged_runs = available_runs.slice(page_start, page_end)

  // Mirror the data-guide review table: show as much content as fits inside
  // a fixed-height clipped box with a fade + "See all" affordance for long
  // strings; the dialog shows the full content.
  const SEE_ALL_CHAR_THRESHOLD = 600
  let see_all_dialog: Dialog
  let see_all_title: string = ""
  let see_all_subtitle: string = ""
  let see_all_content: string = ""

  function show_full_text(title: string, content: string) {
    see_all_title = title
    see_all_content = content
    see_all_dialog?.show()
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
        {#each paged_runs as run}
          {@const input_text = run.input ?? ""}
          {@const output_text = run.output?.output ?? ""}
          {@const input_long = input_text.length > SEE_ALL_CHAR_THRESHOLD}
          {@const output_long = output_text.length > SEE_ALL_CHAR_THRESHOLD}
          <tr>
            <td class="py-2">
              {#if input_long}
                <div class="max-h-[140px] overflow-y-hidden relative">
                  <pre
                    class="whitespace-pre-wrap break-words text-xs text-gray-600">{input_text}</pre>
                  <div class="absolute bottom-0 left-0 w-full">
                    <div
                      class="h-16 bg-gradient-to-t from-white to-transparent"
                    ></div>
                    <div
                      class="text-center bg-white font-medium text-xs text-gray-500"
                    >
                      <button
                        type="button"
                        class="text-gray-500 hover:text-gray-700 underline-offset-2 hover:underline"
                        on:click={() => show_full_text("Input", input_text)}
                      >
                        See all
                      </button>
                    </div>
                  </div>
                </div>
              {:else}
                <pre
                  class="whitespace-pre-wrap break-words text-xs text-gray-600">{input_text}</pre>
              {/if}
            </td>
            <td class="py-2">
              {#if output_long}
                <div class="max-h-[140px] overflow-y-hidden relative">
                  <pre
                    class="whitespace-pre-wrap break-words text-xs text-gray-600">{output_text}</pre>
                  <div class="absolute bottom-0 left-0 w-full">
                    <div
                      class="h-16 bg-gradient-to-t from-white to-transparent"
                    ></div>
                    <div
                      class="text-center bg-white font-medium text-xs text-gray-500"
                    >
                      <button
                        type="button"
                        class="text-gray-500 hover:text-gray-700 underline-offset-2 hover:underline"
                        on:click={() => show_full_text("Output", output_text)}
                      >
                        See all
                      </button>
                    </div>
                  </div>
                </div>
              {:else}
                <pre
                  class="whitespace-pre-wrap break-words text-xs text-gray-600">{output_text}</pre>
              {/if}
            </td>
            <td class="py-2 text-center align-middle">
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

<!-- See-all Dialog: shows the full text of an input/output cell that was
     truncated in the table because it exceeded SEE_ALL_CHAR_THRESHOLD. -->
<Dialog
  bind:this={see_all_dialog}
  title={see_all_title}
  subtitle={see_all_subtitle}
  width="wide"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  <pre
    class="whitespace-pre-wrap break-words text-sm text-gray-600">{see_all_content}</pre>
</Dialog>
