<script lang="ts">
  // Read-only observer view of one sub-agent. Renders the child's messages
  // through the SAME shared transcript component as the main view (full
  // fidelity: kickoff user bubble, markdown, step groups, tool status lines,
  // thinking/retry indicators) under a status header. Composer routing lives in
  // chat.svelte; nothing here mutates the run.
  import type {
    SubAgentItem,
    SubagentRuntimeState,
  } from "$lib/chat/subagent_store"
  import type { ChatMessage } from "$lib/chat/streaming_chat"
  import ChatTranscript from "./chat_transcript.svelte"
  import BrailleSpinner from "./braille_spinner.svelte"

  export let child: SubAgentItem
  export let messages: ChatMessage[] = []
  /** Live affordances mirrored from the child's stream (subagent_store). */
  export let runtime: SubagentRuntimeState | null = null

  const STATUS_LABELS: Record<SubAgentItem["status"], string> = {
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    stopped: "Stopped",
    timeout: "Timed out",
  }
</script>

<div class="flex flex-col gap-4 w-full min-h-full md:max-w-3xl mx-auto px-1">
  <div
    class="sticky top-0 z-10 flex items-center gap-2 bg-base-100 py-2 text-xs text-base-content/60 border-b border-base-content/10"
  >
    <span class="font-medium text-sm text-base-content/80 truncate"
      >{child.name}</span
    >
    <span class="shrink-0 rounded-full bg-base-content/[0.06] px-2 py-0.5"
      >{child.agent_type}</span
    >
    <span
      class="shrink-0 ml-auto {child.status === 'running'
        ? 'text-primary'
        : child.status === 'completed'
          ? 'text-base-content/60'
          : 'text-error/80'}"
    >
      {#if child.status === "running"}
        <span class="inline-flex items-center gap-1.5">
          <BrailleSpinner />
          {STATUS_LABELS[child.status]}
        </span>
      {:else}
        {STATUS_LABELS[child.status]}
      {/if}
    </span>
  </div>
  <ChatTranscript
    {messages}
    loading={child.status === "running"}
    showActivityIndicator={runtime?.showActivityIndicator ?? false}
    retrying={runtime?.retry ?? null}
    readOnly
  />
  <div class="shrink-0 min-h-[24px]" aria-hidden="true" />
</div>
