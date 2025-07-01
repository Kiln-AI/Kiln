<script lang="ts">
  import type { OptionGroup } from "./fancy_select_types"
  import {
    computePosition,
    autoUpdate,
    flip,
    shift,
    offset,
    size,
  } from "@floating-ui/dom"
  import { onMount, onDestroy } from "svelte"

  export let options: OptionGroup[] = []
  export let selected: unknown
  export let empty_label: string = "Select an option"

  // Add this variable to track scrollability
  let isMenuScrollable = false
  let menuElement: HTMLElement
  let dropdownElement: HTMLElement
  let selectedElement: HTMLElement
  let scrolling = false
  let scrollInterval: number | null = null
  let focusedIndex = -1
  let listVisible = false
  let cleanupAutoUpdate: (() => void) | null = null
  let mounted = false
  const id = Math.random().toString(36).substring(2, 15)

  onMount(() => {
    mounted = true
  })

  onDestroy(() => {
    stopScroll()
    if (cleanupAutoUpdate) {
      cleanupAutoUpdate()
    }
  })

  // Select a prompt
  function selectOption(option: unknown) {
    selected = option
    // Delay hiding the dropdown to ensure the click event is fully processed
    setTimeout(() => {
      listVisible = false
    }, 0)
  }

  // Function to check if menu is scrollable
  function checkIfScrollable() {
    if (menuElement) {
      isMenuScrollable = menuElement.scrollHeight > menuElement.clientHeight
    }
  }

  // Create an action to bind to the menu element
  function scrollableCheck(node: HTMLElement) {
    menuElement = node
    checkIfScrollable()

    // Create a mutation observer to detect content changes
    const observer = new MutationObserver(checkIfScrollable)
    observer.observe(node, { childList: true, subtree: true })

    return {
      destroy() {
        observer.disconnect()
      },
    }
  }

  // Watch for changes to options and recheck scrollability
  $: options, setTimeout(checkIfScrollable, 0)

  // Set up floating UI positioning when dropdown becomes visible
  $: if (listVisible && selectedElement && dropdownElement && mounted) {
    setupFloatingPosition()
  } else if (!listVisible && cleanupAutoUpdate) {
    cleanupAutoUpdate()
    cleanupAutoUpdate = null
  }

  function setupFloatingPosition() {
    if (!selectedElement || !dropdownElement) return

    const updatePosition = () => {
      computePosition(selectedElement, dropdownElement, {
        placement: "bottom-start",
        strategy: "fixed",
        middleware: [
          offset(4), // Small gap between trigger and dropdown
          flip(), // Flip to top if not enough space below
          shift({ padding: 8 }), // Shift to stay in viewport
          size({
            apply({ availableHeight, availableWidth: _, elements, rects }) {
              // Get viewport dimensions and reference element position
              const viewportHeight = window.innerHeight
              const referenceRect = rects.reference
              const padding = 10 // 10px from edges

              // Calculate available space below the reference element
              const spaceBelow =
                viewportHeight -
                (referenceRect.y + referenceRect.height) -
                padding

              // Calculate available space above the reference element
              const spaceAbove = referenceRect.y - padding

              // Calculate total available space (what we can use if we grow both ways)
              const totalAvailableSpace = spaceAbove + spaceBelow

              // Determine max height based on our logic:
              // 1. Prefer to fit below if possible
              // 2. Otherwise use total available space (will flip to top or grow both ways)
              let maxHeight
              if (availableHeight <= spaceBelow) {
                // It fits below, use the available space below
                maxHeight = Math.min(availableHeight, spaceBelow)
              } else {
                // It doesn't fit below, use total available space
                maxHeight = Math.min(availableHeight, totalAvailableSpace)
              }

              // Apply maxHeight to the dropdown container
              Object.assign(elements.floating.style, {
                maxHeight: `${maxHeight}px`,
              })

              // Also set a CSS custom property that we can use for the inner menu
              elements.floating.style.setProperty(
                "--dropdown-max-height",
                `${maxHeight - 32}px`,
              ) // Account for padding
            },
            padding: 10, // Match our edge padding
          }),
        ],
      }).then(({ x, y }) => {
        Object.assign(dropdownElement.style, {
          left: `${x}px`,
          top: `${y}px`,
          position: "fixed",
        })
      })
    }

    // Initial positioning
    updatePosition()

    // Set up auto-update with proper options for scroll handling
    cleanupAutoUpdate = autoUpdate(
      selectedElement,
      dropdownElement,
      updatePosition,
      {
        // Enable all update triggers for maximum compatibility
        ancestorScroll: true,
        ancestorResize: true,
        elementResize: true,
        layoutShift: true,
        animationFrame: false, // Set to true if you have animations
      },
    )
  }

  // Add scroll functionality when hovering the indicator
  function startScroll() {
    if (!scrolling && isMenuScrollable) {
      scrolling = true
      scrollInterval = window.setInterval(() => {
        if (menuElement) {
          menuElement.scrollTop += 8

          // Stop scrolling if we've reached the bottom
          if (
            menuElement.scrollTop + menuElement.clientHeight >=
            menuElement.scrollHeight
          ) {
            stopScroll()
          }
        }
      }, 20)
    }
  }

  function stopScroll() {
    scrolling = false
    if (scrollInterval !== null) {
      window.clearInterval(scrollInterval)
      scrollInterval = null
    }
  }

  function scrollToFocusedIndex() {
    if (listVisible && menuElement) {
      const optionElement = document.getElementById(
        `option-${id}-${focusedIndex}`,
      )
      if (optionElement) {
        // Check if the element is fully in view
        const menuRect = menuElement.getBoundingClientRect()
        const optionRect = optionElement.getBoundingClientRect()

        const isInView =
          optionRect.top >= menuRect.top && optionRect.bottom <= menuRect.bottom

        // Only scroll if the element is not in view
        if (!isInView) {
          optionElement.scrollIntoView({ block: "nearest" })
        }
      }
    }
  }

  // Handle click outside to close dropdown
  function handleDocumentClick(event: MouseEvent) {
    if (
      listVisible &&
      selectedElement &&
      !selectedElement.contains(event.target as Node) &&
      dropdownElement &&
      !dropdownElement.contains(event.target as Node)
    ) {
      listVisible = false
    }
  }

  $: if (mounted) {
    if (listVisible) {
      document.addEventListener("click", handleDocumentClick)
    } else {
      document.removeEventListener("click", handleDocumentClick)
    }
  }
</script>

<div class="dropdown w-full relative">
  <div
    tabindex="0"
    role="listbox"
    class="select select-bordered w-full flex items-center {!listVisible
      ? 'focus:ring-2 focus:ring-offset-2 focus:ring-base-300'
      : 'border-none'}"
    bind:this={selectedElement}
    on:mousedown={() => {
      listVisible = true
    }}
    on:blur={(_) => {
      // Only close if focus is not moving to the dropdown
      setTimeout(() => {
        if (
          dropdownElement &&
          !dropdownElement.contains(document.activeElement)
        ) {
          listVisible = false
        }
      }, 0)
    }}
    on:keydown={(event) => {
      if (
        !listVisible &&
        (event.key === "ArrowDown" ||
          event.key === "ArrowUp" ||
          event.key === "Enter")
      ) {
        event.preventDefault()
        listVisible = true
        focusedIndex = 0
        return
      }
      if (event.key === "Escape") {
        event.preventDefault()
        listVisible = false
        return
      }
      if (event.key === "ArrowDown") {
        event.preventDefault()
        focusedIndex = Math.min(
          focusedIndex + 1,
          options.flatMap((group) => group.options).length - 1,
        )
        scrollToFocusedIndex()
      } else if (event.key === "ArrowUp") {
        event.preventDefault()
        focusedIndex = Math.max(focusedIndex - 1, 0)
        scrollToFocusedIndex()
      } else if (event.key === "Enter") {
        selectOption(
          options.flatMap((group) => group.options)[focusedIndex].value,
        )
      }
    }}
  >
    <span class="truncate">
      {(() => {
        const flatOptions = options.flatMap((group) => group.options)
        const selectedOption = flatOptions.find(
          (item) => item.value === selected,
        )
        return selectedOption ? selectedOption.label : empty_label
      })()}
    </span>
  </div>

  {#if listVisible && mounted}
    <div
      bind:this={dropdownElement}
      class="bg-base-100 rounded-box z-[1000] p-2 pt-0 shadow border flex flex-col fixed"
      style="width: {selectedElement?.offsetWidth ||
        0}px; max-height: var(--dropdown-max-height, 300px);"
    >
      <ul
        class="menu overflow-y-auto overflow-x-hidden flex-nowrap pt-0 mt-2 custom-scrollbar flex-1"
        use:scrollableCheck
        style="max-height: calc(var(--dropdown-max-height, 300px) - 1rem);"
      >
        {#each options as option, sectionIndex}
          <li class="menu-title pl-1 sticky top-0 bg-white z-10">
            {option.label}
          </li>
          {#each option.options as item, index}
            {@const overallIndex =
              options
                .slice(0, sectionIndex)
                .reduce((count, group) => count + group.options.length, 0) +
              index}
            <li id={`option-${id}-${overallIndex}`}>
              <button
                role="option"
                aria-selected={focusedIndex === overallIndex}
                class="flex flex-col text-left gap-[1px] pointer-events-auto {focusedIndex ===
                overallIndex
                  ? ' active'
                  : 'hover:bg-transparent'}"
                on:mousedown={(event) => {
                  event.stopPropagation()
                  selectOption(item.value)
                }}
                on:mouseenter={() => {
                  focusedIndex = overallIndex
                }}
              >
                <div class="w-full">
                  {item.label}
                </div>
                {#if item.description}
                  <div class="text-xs font-medium text-base-content/40 w-full">
                    {item.description}
                  </div>
                {/if}
              </button>
            </li>
          {/each}
        {/each}
      </ul>

      <!-- Scroll indicator - only show if scrollable -->
      {#if isMenuScrollable}
        <div class="h-5">&nbsp;</div>
        <!--svelte-ignore a11y-no-static-element-interactions -->
        <div
          class="absolute bottom-0 left-0 right-0 pointer-events-auto rounded-b-md stroke-[2px] hover:stroke-[4px] border-t border-base-200"
          on:mouseenter={startScroll}
          on:mouseleave={stopScroll}
        >
          <div
            class="bg-gradient-to-b from-transparent to-white w-full flex justify-center items-center py-1 cursor-pointer rounded-b-xl"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="opacity-60"
            >
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  /* Custom scrollbar styling */
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }

  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }

  .custom-scrollbar::-webkit-scrollbar-thumb {
    background-color: rgba(115, 115, 115, 0.5);
    border-radius: 20px;
  }

  /* Firefox */
  .custom-scrollbar {
    scrollbar-width: thin;
    scrollbar-color: rgba(115, 115, 115, 0.5) transparent;
  }
</style>
