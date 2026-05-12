<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import {
    formatExpandedContent,
    type ExpandedContent,
  } from "$lib/utils/format_expanded_content"

  let dialog: Dialog
  let title: string = ""
  let content: ExpandedContent = { value: "", isJson: false }

  export function show(dialog_title: string, raw: string) {
    title = dialog_title
    content = formatExpandedContent(raw)
    dialog?.show()
  }
</script>

<svelte:head>
  <link rel="stylesheet" href="/styles/highlightjs.min.css" />
</svelte:head>

<Dialog
  bind:this={dialog}
  {title}
  width="wide"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  {#if content.isJson}
    <!-- eslint-disable svelte/no-at-html-tags -->
    <pre
      class="whitespace-pre-wrap break-words text-sm text-gray-600">{@html content.value}</pre>
    <!-- eslint-enable svelte/no-at-html-tags -->
  {:else}
    <pre
      class="whitespace-pre-wrap break-words text-sm text-gray-600">{content.value}</pre>
  {/if}
</Dialog>
