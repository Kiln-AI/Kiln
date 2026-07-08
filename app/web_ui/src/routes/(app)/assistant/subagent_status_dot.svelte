<script lang="ts">
  import type { SubAgentStatus } from "$lib/chat/subagent_store"

  export let status: SubAgentStatus

  const LABELS: Record<SubAgentStatus, string> = {
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    stopped: "Stopped",
    timeout: "Timed out",
  }

  // Live state as a colored dot: pulsing green while running; solid green /
  // red / gray / amber for the terminal states.
  const COLORS: Record<SubAgentStatus, string> = {
    running: "bg-success",
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
