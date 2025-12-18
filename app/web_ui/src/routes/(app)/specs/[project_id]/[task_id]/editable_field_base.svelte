<script lang="ts" generics="T">
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
  import type { Spec } from "$lib/types"
  import { computePosition, autoUpdate, offset } from "@floating-ui/dom"
  import { onMount, onDestroy } from "svelte"

  export let spec: Spec
  export let currentValue: T
  export let options: OptionGroup[]
  export let aria_label: string
  export let formatDisplay: (value: T) => string
  export let onUpdate: (spec: Spec, value: T) => void
  export let dropdownWidth: string = "w-24"
  export let compact: boolean = false
  export let onOpen: (() => void) | undefined = undefined
  export let always_show_border: boolean = false

  let lastUpdateTime = 0
  let isEditing = false
  let dropdownElement: HTMLElement
  let triggerElement: HTMLElement
  let cleanupAutoUpdate: (() => void) | null = null
  let mounted = false
  let isHovered = false
  let clickListenerTimeoutId: ReturnType<typeof setTimeout> | null = null
  let pendingStopTimer: ReturnType<typeof setTimeout> | null = null
  let pendingCompleteTimer: ReturnType<typeof setTimeout> | null = null

  $: displayText = formatDisplay(currentValue)

  function handleValueChange() {
    if (isEditing) {
      const now = Date.now()
      if (now - lastUpdateTime > 300) {
        lastUpdateTime = now
        onUpdate(spec, currentValue)
      }
    }
  }

  export function triggerUpdate() {
    handleValueChange()
  }

  export function setPendingComplete() {
    if (pendingCompleteTimer !== null) {
      clearTimeout(pendingCompleteTimer)
    }
    pendingCompleteTimer = setTimeout(() => {
      pendingCompleteTimer = null
      isEditing = false
    }, 100)
  }

  function startEditing() {
    isEditing = true
    onOpen?.()
  }

  function stopEditing() {
    if (pendingStopTimer !== null) {
      clearTimeout(pendingStopTimer)
      pendingStopTimer = null
    }
    if (pendingCompleteTimer !== null) {
      clearTimeout(pendingCompleteTimer)
      pendingCompleteTimer = null
    }
    isEditing = false
  }

  export function close() {
    stopEditing()
  }

  function getFlatOptions(): Option[] {
    return options.flatMap((group) => group.options)
  }

  function selectOption(value: unknown) {
    currentValue = value as T
    handleValueChange()
    if (pendingStopTimer !== null) {
      clearTimeout(pendingStopTimer)
    }
    pendingStopTimer = setTimeout(() => {
      pendingStopTimer = null
      stopEditing()
    }, 100)
  }

  $: if (isEditing && triggerElement && dropdownElement && mounted) {
    setupFloatingPosition()
  } else if (!isEditing && cleanupAutoUpdate) {
    cleanupAutoUpdate()
    cleanupAutoUpdate = null
  }

  function setupFloatingPosition() {
    if (!triggerElement || !dropdownElement) return

    const updatePosition = () => {
      computePosition(triggerElement, dropdownElement, {
        placement: "bottom-start",
        strategy: "fixed",
        middleware: [offset(2)],
      }).then(({ x, y }) => {
        Object.assign(dropdownElement.style, {
          left: `${x}px`,
          top: `${y}px`,
        })
      })
    }

    updatePosition()
    cleanupAutoUpdate = autoUpdate(
      triggerElement,
      dropdownElement,
      updatePosition,
    )
  }

  onMount(() => {
    mounted = true
  })

  onDestroy(() => {
    if (cleanupAutoUpdate) {
      cleanupAutoUpdate()
    }
    if (clickListenerTimeoutId !== null) {
      clearTimeout(clickListenerTimeoutId)
      clickListenerTimeoutId = null
    }
    if (pendingStopTimer !== null) {
      clearTimeout(pendingStopTimer)
      pendingStopTimer = null
    }
    if (pendingCompleteTimer !== null) {
      clearTimeout(pendingCompleteTimer)
      pendingCompleteTimer = null
    }
    document.removeEventListener("click", handleClickOutside)
  })

  function handleClickOutside(event: MouseEvent) {
    if (
      isEditing &&
      triggerElement &&
      dropdownElement &&
      !triggerElement.contains(event.target as Node) &&
      !dropdownElement.contains(event.target as Node)
    ) {
      stopEditing()
    }
  }

  $: if (isEditing) {
    if (clickListenerTimeoutId !== null) {
      clearTimeout(clickListenerTimeoutId)
    }
    clickListenerTimeoutId = setTimeout(() => {
      clickListenerTimeoutId = null
      document.addEventListener("click", handleClickOutside)
    }, 0)
  } else {
    if (clickListenerTimeoutId !== null) {
      clearTimeout(clickListenerTimeoutId)
      clickListenerTimeoutId = null
    }
    document.removeEventListener("click", handleClickOutside)
  }
</script>

<div class="relative" bind:this={triggerElement}>
  <div
    class="cursor-pointer rounded inline-block transition-all {isHovered ||
    always_show_border
      ? 'border border-base-content border-opacity-30'
      : 'border border-transparent'} {compact
      ? 'px-1'
      : 'px-2 py-1'} {always_show_border && isHovered ? 'bg-base-200' : ''}"
    aria-label={aria_label}
    on:click={(e) => {
      e.stopPropagation()
      if (!isEditing) {
        startEditing()
      }
    }}
    on:mouseenter={(e) => {
      e.stopPropagation()
      isHovered = true
    }}
    on:mouseleave={() => {
      isHovered = false
    }}
    role="button"
    tabindex="0"
    on:keydown={(e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault()
        if (!isEditing) {
          startEditing()
        }
      }
    }}
  >
    {displayText}
  </div>

  {#if isEditing && mounted}
    <div
      bind:this={dropdownElement}
      class="bg-base-100 rounded-box z-[1000] p-2 shadow border flex flex-col fixed {dropdownWidth}"
      on:click={(e) => e.stopPropagation()}
      role="presentation"
    >
      <ul class="menu menu-sm w-full">
        {#each getFlatOptions() as item}
          <li>
            <button
              type="button"
              class="w-full text-left {currentValue === item.value
                ? 'bg-base-200'
                : ''}"
              on:click={() => selectOption(item.value)}
              disabled={item.disabled}
            >
              {item.label}
            </button>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</div>
