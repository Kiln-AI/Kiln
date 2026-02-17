<script lang="ts">
  import {
    autoUpdate,
    computePosition,
    flip,
    offset,
    shift,
    type Placement,
    type Strategy,
  } from "@floating-ui/dom"
  import { onDestroy, onMount, tick } from "svelte"

  export let placement: Placement = "bottom-end"
  export let strategy: Strategy = "fixed"
  export let offset_px = 0
  export let shift_padding = 8
  export let role = "menu"

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
    updatePosition()
    startAutoUpdate()
  })

  onDestroy(() => {
    stopAutoUpdate()
  })
</script>

<div bind:this={contentElement} class="fixed z-50" {role}>
  <slot />
</div>
