<script lang="ts">
  import type { RunState } from "$lib/chat/conversation_store"

  export let status: RunState

  // The unified RunState vocabulary. Sub-agent children only ever surface
  // running + the four terminal states (same strings as the old
  // SubAgentStatus, so the visuals are unchanged); idle/awaiting_approval
  // exist for the parent kinds that join the store in phases 3-4 and are
  // mapped defensively here.
  const LABELS: Record<RunState, string> = {
    idle: "Idle",
    running: "Running",
    awaiting_approval: "Waiting for approval",
    completed: "Completed",
    failed: "Failed",
    stopped: "Stopped",
    timeout: "Timed out",
  }

  // Live state as a colored dot: pulsing green while running; solid green /
  // red / gray / amber for the terminal states.
  const COLORS: Record<RunState, string> = {
    idle: "bg-base-content/30",
    running: "bg-success",
    awaiting_approval: "bg-warning",
    completed: "bg-success",
    failed: "bg-error",
    stopped: "bg-base-content/30",
    timeout: "bg-warning",
  }
</script>

<span
  class="size-2 shrink-0 rounded-full {COLORS[status]}"
  class:status-dot-pulse={status === "running"}
  title={LABELS[status]}
  aria-label={LABELS[status]}
  role="img"
></span>

<style>
  .status-dot-pulse {
    animation: status-dot-pulse 1.6s ease-in-out infinite;
  }

  @keyframes status-dot-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.4;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .status-dot-pulse {
      animation: none;
    }
  }
</style>
