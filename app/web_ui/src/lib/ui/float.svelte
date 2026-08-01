<script lang="ts">
  import {
    autoUpdate,
    computePosition,
    flip,
    offset,
    shift,
    size,
    type Placement,
    type Strategy,
  } from "@floating-ui/dom"
  import { onDestroy, onMount, tick } from "svelte"

  export let placement: Placement = "bottom-end"
  export let strategy: Strategy = "fixed"
  export let offset_px = 0
  export let shift_padding = 8
  // Pass "none" to omit the role attribute entirely (let the slotted content
  // carry its own semantics).
  export let role: string = "menu"
  export let portal = false
  export let aria_label: string | undefined = undefined

  let referenceElement: HTMLElement | null = null
  let contentElement: HTMLElement
  let cleanupAutoUpdate: (() => void) | null = null

  function updatePosition() {
    if (!referenceElement || !contentElement) return
    computePosition(referenceElement, contentElement, {
      placement,
      strategy,
      middleware: [
        offset(offset_px),
        flip(),
        shift({ padding: shift_padding }),
        // How much room the chosen placement actually leaves, published as a
        // custom property rather than written straight onto the element.
        // Content taller than the viewport otherwise has nowhere to go: flip
        // picks the roomier side, and when neither side is roomy enough it
        // still overruns, with the part that overruns unreachable. Only the
        // slotted content knows what to do about that - scroll, truncate, or
        // nothing - so this reports the budget and lets it decide. Last in the
        // chain, so it measures the placement flip and shift settled on.
        size({
          padding: shift_padding,
          apply({ availableHeight, elements }) {
            elements.floating.style.setProperty(
              "--float-available-height",
              `${Math.max(availableHeight, 0)}px`,
            )
          },
        }),
      ],
    }).then(({ x, y }) => {
      if (!contentElement) return
      Object.assign(contentElement.style, {
        left: `${x}px`,
        top: `${y}px`,
      })
    })
  }

  function startAutoUpdate() {
    if (!referenceElement || !contentElement || cleanupAutoUpdate) return
    cleanupAutoUpdate = autoUpdate(
      referenceElement,
      contentElement,
      updatePosition,
    )
  }

  function stopAutoUpdate() {
    if (!cleanupAutoUpdate) return
    cleanupAutoUpdate()
    cleanupAutoUpdate = null
  }

  onMount(async () => {
    await tick()
    referenceElement = contentElement.parentElement
    if (!referenceElement) return
    if (portal) {
      document.body.appendChild(contentElement)
    }
    updatePosition()
    startAutoUpdate()
  })

  onDestroy(() => {
    stopAutoUpdate()
    if (portal) {
      contentElement?.remove()
    }
  })
</script>

<div
  bind:this={contentElement}
  class="z-50 {strategy === 'fixed' ? 'fixed' : 'absolute'}"
  role={role === "none" ? undefined : role}
  aria-label={aria_label}
>
  <slot />
</div>
