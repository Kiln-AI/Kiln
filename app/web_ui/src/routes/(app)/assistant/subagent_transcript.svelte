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
  import ChatStatusSteps from "./chat_status_steps.svelte"
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

  $: running = child.status === "running"
  $: lastMessage = messages[messages.length - 1]
  // The activity indicator drives the shared transcript's thinking dots between
  // rounds. The per-child runtime is processor-driven, so it doesn't exist
  // until the first live event arrives — default it ON while the child is
  // running (the backend IS working), and let the processor state take over
  // once events flow.
  $: effectiveActivityIndicator = runtime
    ? runtime.showActivityIndicator
    : running
  // No in-progress assistant output at the tail of the transcript: empty, or a
  // user message (kickoff briefing / steer) is last. The shared transcript only
  // hosts its thinking indicator inside the LAST ASSISTANT message, so a
  // running child with a user tail needs this standalone one — otherwise a
  // just-started child shows the kickoff bubble and looks stuck. Suppressed
  // while retrying: chat_transcript's fallback indicator covers that case
  // (exactly one busy indicator shows).
  $: awaitingAssistant =
    running && lastMessage?.role !== "assistant" && !runtime?.retry
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
    loading={running}
    showActivityIndicator={effectiveActivityIndicator}
    retrying={runtime?.retry ?? null}
    readOnly
  />
  {#if awaitingAssistant}
    <!-- Running with no assistant output at the tail (empty transcript, or the
       kickoff/steer bubble is last while the first response is still being
       generated): show the same thinking indicator the transcript uses so the
       child never looks stuck. -->
    <div class="flex items-start gap-3" role="status">
      <img
        src="/images/chat_icon_animated.svg"
        alt=""
        class="w-9 h-9 shrink-0 -mt-1.5"
      />
      <div class="flex flex-col">
        <ChatStatusSteps
          parts={[]}
          isLoading={true}
          isLastMessage={true}
          showActivityIndicator={true}
          retrying={null}
        />
      </div>
    </div>
  {/if}
  <div class="shrink-0 min-h-[24px]" aria-hidden="true" />
</div>
