<script lang="ts">
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
  import type { Spec, SpecStatus } from "$lib/types"
  import { formatPriority } from "$lib/utils/formatters"
  import { capitalize } from "$lib/utils/formatters"
  import { computePosition, autoUpdate, offset } from "@floating-ui/dom"
  import { onMount, onDestroy } from "svelte"

  export let spec: Spec
  export let field: "priority" | "status"
  export let options: OptionGroup[]
  export let aria_label: string = ""
  export let onUpdate: (spec: Spec, value: number | SpecStatus) => void
  export let compact: boolean = false
  export let onOpen: (() => void) | undefined = undefined

  let currentValue: number | SpecStatus =
    field === "priority" ? spec.priority : spec.status
  let lastSyncedSpecValue: number | SpecStatus =
    field === "priority" ? spec.priority : spec.status
  let lastUpdateTime = 0
  let isEditing = false
  let hasPendingUpdate = false
  let dropdownElement: HTMLElement
  let triggerElement: HTMLElement
  let cleanupAutoUpdate: (() => void) | null = null
  let mounted = false
  let isHovered = false

  $: widthClass = field === "priority" ? "w-24" : "w-32"
  $: specValue = field === "priority" ? spec.priority : spec.status
  $: displayText =
    field === "priority"
      ? formatPriority(currentValue as number)
      : capitalize(currentValue as SpecStatus)

  $: {
    if (specValue !== lastSyncedSpecValue) {
      lastSyncedSpecValue = specValue
      currentValue = specValue
      if (hasPendingUpdate) {
        hasPendingUpdate = false
        setTimeout(() => {
          isEditing = false
        }, 100)
      }
    }
  }

  function handleValueChange() {
    if (currentValue !== lastSyncedSpecValue && isEditing) {
      const now = Date.now()
      if (now - lastUpdateTime > 300) {
        lastUpdateTime = now
        hasPendingUpdate = true
        onUpdate(spec, currentValue)
      }
    }
  }

  $: if (isEditing) {
    handleValueChange()
  }

  function startEditing() {
    isEditing = true
    onOpen?.()
  }

  function stopEditing() {
    isEditing = false
  }

  export function close() {
    stopEditing()
  }

  function getFlatOptions(): Option[] {
    return options.flatMap((group) => group.options)
  }

  function selectOption(option: unknown) {
    currentValue = option as number | SpecStatus
    if (currentValue !== lastSyncedSpecValue) {
      const now = Date.now()
      if (now - lastUpdateTime > 300) {
        lastUpdateTime = now
        hasPendingUpdate = true
        onUpdate(spec, currentValue)
      }
    }
    setTimeout(() => {
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
    setTimeout(() => {
      document.addEventListener("click", handleClickOutside)
    }, 0)
  } else {
    document.removeEventListener("click", handleClickOutside)
  }
</script>

<div class="relative" bind:this={triggerElement}>
  <div
    class="cursor-pointer rounded inline-block transition-all {isHovered
      ? 'border border-base-content border-opacity-30'
      : 'border border-transparent'} {compact ? 'px-1' : 'px-2 py-1'}"
    aria-label={aria_label || (field === "priority" ? "Priority" : "Status")}
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
      class="bg-base-100 rounded-box z-[1000] p-2 shadow border flex flex-col fixed"
      style="width: {widthClass === 'w-24' ? '96px' : '128px'};"
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
