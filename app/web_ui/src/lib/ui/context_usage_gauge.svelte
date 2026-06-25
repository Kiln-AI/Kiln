<script lang="ts">
  import {
    computePosition,
    autoUpdate,
    offset,
    flip,
    shift,
  } from "@floating-ui/dom"
  import { onDestroy, tick } from "svelte"
  import type { ContextUsage } from "$lib/chat/streaming_chat"

  // ``null`` before the first assistant turn completes — the gauge is hidden
  // until the first ``context_usage`` arrives.
  export let usage: ContextUsage | null = null

  // Raw percent may momentarily exceed 100 just before a compaction triggers;
  // the displayed number is clamped to 100. The bar is a single neutral grey at
  // all percentages (no color ramp).
  $: displayPercent = Math.min(
    100,
    Math.round((usage?.context_percent ?? 0) * 100),
  )

  $: tooltipText = usage
    ? `≈ ${displayPercent}% of context used (≈ ${usage.context_tokens.toLocaleString()} / ${usage.context_limit.toLocaleString()} tokens). Older messages are automatically summarized when the conversation gets long.`
    : ""

  let triggerElement: HTMLDivElement | undefined
  let tooltipElement: HTMLDivElement | undefined
  let isVisible = false
  let cleanupAutoUpdate: (() => void) | null = null

  async function showTooltip() {
    if (!triggerElement || !tooltipElement) return
    // Avoid leaking/overwriting a previous autoUpdate registration.
    if (cleanupAutoUpdate) {
      cleanupAutoUpdate()
      cleanupAutoUpdate = null
    }
    isVisible = true
    // Wait for Svelte to render the tooltip (remove ``hidden``) so Floating UI
    // can measure its real size instead of 0×0.
    await tick()
    // The pointer may have left during the await; bail if we hid in the meantime.
    if (!isVisible) return
    const updatePosition = () => {
      if (!triggerElement || !tooltipElement) return
      computePosition(triggerElement, tooltipElement, {
        placement: "top",
        strategy: "fixed",
        middleware: [offset(6), flip(), shift({ padding: 8 })],
      }).then(({ x, y }) => {
        if (tooltipElement) {
          Object.assign(tooltipElement.style, {
            left: `${x}px`,
            top: `${y}px`,
          })
        }
      })
    }
    updatePosition()
    cleanupAutoUpdate = autoUpdate(
      triggerElement,
      tooltipElement,
      updatePosition,
    )
  }

  function hideTooltip() {
    isVisible = false
    if (cleanupAutoUpdate) {
      cleanupAutoUpdate()
      cleanupAutoUpdate = null
    }
  }

  onDestroy(() => {
    if (cleanupAutoUpdate) cleanupAutoUpdate()
  })
</script>

{#if usage}
  <div
    bind:this={triggerElement}
    class="flex flex-col items-end gap-0.5 cursor-default"
    role="meter"
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={displayPercent}
    aria-label={`Approximately ${displayPercent}% of context used`}
    data-testid="context-usage-gauge"
    on:mouseenter={showTooltip}
    on:mouseleave={hideTooltip}
  >
    <span
      class="text-xs font-medium text-base-content/70 tabular-nums whitespace-nowrap leading-none"
      data-testid="context-usage-percent"
    >
      ≈{displayPercent}%
    </span>
    <div
      class="w-16 md:w-20 h-1.5 rounded-full bg-base-content/10 overflow-hidden"
      data-testid="context-usage-track"
    >
      <div
        class="h-full rounded-full bg-base-content/30 transition-[width] duration-300"
        style="width: {displayPercent}%"
        data-testid="context-usage-fill"
      ></div>
    </div>
  </div>

  <div
    bind:this={tooltipElement}
    class="fixed z-[50] px-3 py-2 text-xs text-base-content bg-stone-200 rounded-md shadow-lg w-64 whitespace-normal {isVisible
      ? ''
      : 'hidden'}"
    role="tooltip"
    on:mouseenter={showTooltip}
    on:mouseleave={hideTooltip}
  >
    {tooltipText}
  </div>
{/if}
