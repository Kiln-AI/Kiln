<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { TaskRun } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import ClampedText from "$lib/ui/clamped_text.svelte"
  import {
    formatExpandedContent,
    type ExpandedContent,
  } from "$lib/utils/format_expanded_content"

  export let available_runs: TaskRun[] = []

  const PAGE_SIZE = 5
  let current_page = 0
  $: total_pages = Math.ceil(available_runs.length / PAGE_SIZE)
  $: page_start = current_page * PAGE_SIZE
  $: page_end = Math.min(page_start + PAGE_SIZE, available_runs.length)
  $: paged_runs = available_runs.slice(page_start, page_end)

  // Long inputs/outputs are clamped to 3 lines with a "See all" link that
  // pops the full content in a dialog.
  let see_all_dialog: Dialog
  let see_all_title: string = ""
  let see_all_content: ExpandedContent = { value: "", isJson: false }

  function show_full_text(title: string, content: string) {
    see_all_title = title
    see_all_content = formatExpandedContent(content)
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
          {@const input_content = formatExpandedContent(input_text)}
          {@const output_content = formatExpandedContent(output_text)}
          <tr>
            <td class="py-2">
              <ClampedText
                content={input_content.isJson ? "" : input_content.value}
                html_content={input_content.isJson ? input_content.value : null}
                text_class="whitespace-pre-wrap break-words text-xs text-gray-600"
                on:see_all={() => show_full_text("Input", input_text)}
              />
            </td>
            <td class="py-2">
              <ClampedText
                content={output_content.isJson ? "" : output_content.value}
                html_content={output_content.isJson
                  ? output_content.value
                  : null}
                text_class="whitespace-pre-wrap break-words text-xs text-gray-600"
                on:see_all={() => show_full_text("Output", output_text)}
              />
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

<head>
  <link rel="stylesheet" href="/styles/highlightjs.min.css" />
</head>

<Dialog
  bind:this={see_all_dialog}
  title={see_all_title}
  width="wide"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  {#if see_all_content.isJson}
    <!-- eslint-disable svelte/no-at-html-tags -->
    <pre
      class="whitespace-pre-wrap break-words text-sm text-gray-600">{@html see_all_content.value}</pre>
    <!-- eslint-enable svelte/no-at-html-tags -->
  {:else}
    <pre
      class="whitespace-pre-wrap break-words text-sm text-gray-600">{see_all_content.value}</pre>
  {/if}
</Dialog>
