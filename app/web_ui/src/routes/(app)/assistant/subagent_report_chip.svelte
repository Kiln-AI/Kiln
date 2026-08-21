<script lang="ts">
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import type { SubagentReportInfo } from "$lib/chat/streaming_chat"

  export let report: SubagentReportInfo
  export let body: string = ""

  let expanded = false

  const STATUS_LABELS: Record<string, string> = {
    completed: "completed",
    failed: "failed",
    stopped: "stopped",
    timeout: "timed out",
  }

  $: statusLabel = STATUS_LABELS[report.status] ?? report.status
</script>

<div class="rounded-lg border border-base-content/10 bg-base-200/60 text-sm">
  <button
    type="button"
    class="flex w-full items-center gap-2 px-3 py-2 text-left"
    on:click={() => (expanded = !expanded)}
    aria-expanded={expanded}
  >
    <span
      class="inline-block w-3 shrink-0 text-center text-xs text-base-content/50"
      aria-hidden="true">{expanded ? "▼" : "▶"}</span
    >
    <span class="min-w-0 flex-1 truncate">
      <span class="font-medium">Sub-agent report</span>
      {#if report.title}
        <span class="text-base-content/70">— {report.title}</span>
      {/if}
      <span class="text-base-content/50">({statusLabel})</span>
    </span>
  </button>
  {#if expanded}
    <div class="border-t border-base-content/10 px-3 py-2">
      <ChatMarkdown text={body} />
    </div>
  {/if}
</div>
