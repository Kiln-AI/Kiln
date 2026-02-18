<script lang="ts">
  import {
    computePosition,
    autoUpdate,
    offset,
    flip,
    shift,
  } from "@floating-ui/dom"
  import { onDestroy } from "svelte"

  export let tooltip_text: string
  export let position: "left" | "right" | "bottom" | "top" = "left"
  export let no_pad = false
  export let symbol: "exclaim" | "info" = "info"

  let triggerElement: HTMLButtonElement
  let tooltipElement: HTMLDivElement
  let isVisible = false
  let cleanupAutoUpdate: (() => void) | null = null

  type Segment =
    | { type: "text"; content: string }
    | { type: "bold"; content: string }
    | { type: "link"; text: string; url: string }

  // Parse a line of text into segments for safe rendering
  function parseLineToSegments(text: string): Segment[] {
    const segments: Segment[] = []
    // Combined regex to match links or bold text
    const pattern = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g
    let lastIndex = 0
    let match

    while ((match = pattern.exec(text)) !== null) {
      // Add plain text before this match
      if (match.index > lastIndex) {
        segments.push({
          type: "text",
          content: text.slice(lastIndex, match.index),
        })
      }

      if (match[1] !== undefined && match[2] !== undefined) {
        // Link: [text](url) - match[1] is text, match[2] is url
        segments.push({ type: "link", text: match[1], url: match[2] })
      } else if (match[3] !== undefined) {
        // Bold: **text** - match[3] is the bold content
        segments.push({ type: "bold", content: match[3] })
      }

      lastIndex = pattern.lastIndex
    }

    // Add remaining plain text
    if (lastIndex < text.length) {
      segments.push({ type: "text", content: text.slice(lastIndex) })
    }

    // If no segments were added, return the whole text as plain
    if (segments.length === 0) {
      segments.push({ type: "text", content: text })
    }

    return segments
  }

  function showTooltip() {
    if (!triggerElement || !tooltipElement) return

    const updatePosition = () => {
      computePosition(triggerElement, tooltipElement, {
        placement: position,
        strategy: "fixed",
        middleware: [
          offset(0), // Gap between trigger and tooltip
          flip(), // Flip to opposite side if no room
          shift({ padding: 8 }), // Shift along axis to stay in viewport
        ],
      }).then(({ x, y }) => {
        if (tooltipElement) {
          Object.assign(tooltipElement.style, {
            left: `${x}px`,
            top: `${y}px`,
          })
        }
      })
    }

    // Initial positioning
    updatePosition()

    // Auto-update position on scroll/resize
    cleanupAutoUpdate = autoUpdate(
      triggerElement,
      tooltipElement,
      updatePosition,
    )

    isVisible = true
  }

  function hideTooltip() {
    isVisible = false
    if (cleanupAutoUpdate) {
      cleanupAutoUpdate()
      cleanupAutoUpdate = null
    }
  }

  onDestroy(() => {
    if (cleanupAutoUpdate) {
      cleanupAutoUpdate()
    }
  })
</script>

<button
  bind:this={triggerElement}
  on:mouseenter={showTooltip}
  on:mouseleave={hideTooltip}
  on:focus={showTooltip}
  on:blur={hideTooltip}
>
  <svg
    fill="currentColor"
    class="w-6 h-6 inline {no_pad ? 'mt-[-3px] ml-[-3px]' : ''} {symbol ===
    'exclaim'
      ? 'rotate-180'
      : ''}"
    viewBox="0 0 1024 1024"
    version="1"
    xmlns="http://www.w3.org/2000/svg"
    ><path
      d="M512 717a205 205 0 1 0 0-410 205 205 0 0 0 0 410zm0 51a256 256 0 1 1 0-512 256 256 0 0 1 0 512z"
    /><path
      d="M485 364c7-7 16-11 27-11s20 4 27 11c8 8 11 17 11 28 0 10-3 19-11 27-7 7-16 11-27 11s-20-4-27-11c-8-8-11-17-11-27 0-11 3-20 11-28zM479 469h66v192h-66z"
    /></svg
  >
</button>

<!-- Custom Floating Tooltip -->
<div
  bind:this={tooltipElement}
  class="fixed z-[50] px-3 py-2 text-sm text-base-content bg-stone-200 rounded-md shadow-lg w-72 whitespace-normal text-center flex flex-col gap-1 {isVisible
    ? ''
    : 'hidden'}"
  role="tooltip"
  on:mouseenter={showTooltip}
  on:mouseleave={hideTooltip}
>
  {#each tooltip_text.replace(/\\n/g, "\n").split("\n") as line}
    {#if line.trim() !== ""}
      <p>
        {#each parseLineToSegments(line) as segment}
          {#if segment.type === "text"}
            {segment.content}
          {:else if segment.type === "bold"}
            <strong>{segment.content}</strong>
          {:else if segment.type === "link"}
            <a
              href={segment.url}
              target="_blank"
              rel="noopener noreferrer"
              class="link"
            >
              {segment.text}
            </a>
          {/if}
        {/each}
      </p>
    {:else}
      <p class="h-2"></p>
    {/if}
  {/each}
</div>
