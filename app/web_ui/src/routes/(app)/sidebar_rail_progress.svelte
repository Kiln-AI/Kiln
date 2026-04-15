<script lang="ts" context="module">
  import type { ProgressUIState } from "$lib/stores/progress_ui_store"

  export function computePercentComplete(
    state: ProgressUIState | null,
  ): number {
    if (!state) return 0
    if (typeof state.progress === "number") {
      return Math.max(0, Math.min(100, Math.round(state.progress * 100)))
    }
    if (
      typeof state.step_count === "number" &&
      typeof state.current_step === "number" &&
      state.step_count > 0
    ) {
      return Math.max(
        0,
        Math.min(
          100,
          Math.round((state.current_step / state.step_count) * 100),
        ),
      )
    }
    return 0
  }
</script>

<script lang="ts">
  import { onDestroy } from "svelte"
  import { goto } from "$app/navigation"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import ProgressWidget from "$lib/ui/progress_widget.svelte"
  import Float from "$lib/ui/float.svelte"

  $: percentComplete = computePercentComplete($progress_ui_state)

  let hovered = false
  let focused = false
  let tooltip_hovered = false
  let tooltip_focused = false
  let show_tooltip = false
  let hide_timer: ReturnType<typeof setTimeout> | null = null
  const HIDE_DELAY_MS = 150

  $: {
    const should_show =
      !!$progress_ui_state &&
      (hovered || focused || tooltip_hovered || tooltip_focused)
    if (should_show) {
      if (hide_timer) {
        clearTimeout(hide_timer)
        hide_timer = null
      }
      show_tooltip = true
    } else if (show_tooltip && hide_timer === null) {
      hide_timer = setTimeout(() => {
        show_tooltip = false
        hide_timer = null
      }, HIDE_DELAY_MS)
    }
  }

  onDestroy(() => {
    if (hide_timer) {
      clearTimeout(hide_timer)
      hide_timer = null
    }
  })

  function handleClick() {
    if ($progress_ui_state?.link) {
      goto($progress_ui_state.link)
    }
  }

  const tooltipId = `sidebar-rail-progress-tooltip-${crypto.randomUUID()}`
</script>

{#if $progress_ui_state}
  <div class="flex justify-center relative py-1 xl:py-2">
    <div
      role="presentation"
      on:mouseenter={() => (hovered = true)}
      on:mouseleave={() => (hovered = false)}
      on:focusin={() => (focused = true)}
      on:focusout={() => (focused = false)}
    >
      <button
        type="button"
        class="w-8 h-8 flex items-center justify-center"
        aria-label="In progress"
        aria-describedby={show_tooltip ? tooltipId : undefined}
        on:click={handleClick}
      >
        <div
          class="radial-progress slow-spin text-primary"
          style="--value:{percentComplete}; --size:1.25rem; --thickness:4px;"
          role="progressbar"
          aria-valuenow={percentComplete}
          aria-valuemin="0"
          aria-valuemax="100"
        ></div>
      </button>
      {#if show_tooltip}
        <Float placement="right" role="region" aria_label="Progress" portal>
          <!-- pl-2 bridges the 8px gap so the cursor can transit from trigger to tooltip without dismissing -->
          <div
            id={tooltipId}
            class="pl-2"
            role="presentation"
            on:mouseenter={() => (tooltip_hovered = true)}
            on:mouseleave={() => (tooltip_hovered = false)}
            on:focusin={() => (tooltip_focused = true)}
            on:focusout={() => (tooltip_focused = false)}
          >
            <div class="w-56 rounded-md">
              <ProgressWidget />
            </div>
          </div>
        </Float>
      {/if}
    </div>
  </div>
{/if}

<style>
  .slow-spin {
    animation: slow-spin 5s linear infinite;
  }
  @keyframes slow-spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
</style>
