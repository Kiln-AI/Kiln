<script lang="ts">
  import type { OptionGroup } from "./fancy_select_types"
  import {
    computePosition,
    autoUpdate,
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

  // Search functionality variables
  let searchText = ""
  let isSearching = false
  let searchInputElement: HTMLInputElement

  // Computed filtered options based on search
  $: filteredOptions = searchText.trim()
    ? options
        .map((group) => ({
          ...group,
          options: group.options.filter(
            (option) =>
              option.label.toLowerCase().includes(searchText.toLowerCase()) ||
              (option.description &&
                option.description
                  .toLowerCase()
                  .includes(searchText.toLowerCase())),
          ),
        }))
        .filter((group) => group.options.length > 0)
    : options

  // Reset search when dropdown closes
  $: if (!listVisible) {
    searchText = ""
    isSearching = false
  }

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

  // Threshold for when to start expanding upward (adjust as needed)
  const minSpaceThreshold = 1200

  function setupFloatingPosition() {
    if (!selectedElement || !dropdownElement) return

    const updatePosition = () => {
      computePosition(selectedElement, dropdownElement, {
        placement: "bottom-start",
        strategy: "fixed",
        middleware: [
          offset(2), // Small gap between trigger and dropdown
          // Custom positioning middleware to handle expansion upward instead of flipping
          {
            name: "customPositioning",
            fn: ({ x, y, rects, elements: _ }) => {
              const viewportHeight = window.innerHeight
              const referenceRect = rects.reference
              const padding = 10

              // Calculate available spaces
              const spaceBelow =
                viewportHeight -
                (referenceRect.y + referenceRect.height) -
                padding

              if (spaceBelow >= minSpaceThreshold) {
                // Enough space below, position normally below the reference
                return { x, y }
              } else {
                // Not enough space below, position to start from top of viewport
                const targetY = padding
                return { x, y: targetY }
              }
            },
          },
          shift({ padding: 8 }), // Shift to stay in viewport horizontally
          size({
            apply({ availableHeight, availableWidth, elements, rects }) {
              // Get viewport dimensions and reference element position
              const viewportHeight = window.innerHeight
              const referenceRect = rects.reference
              const padding = 10 // 10px from edges

              // Calculate available space below the reference element
              const spaceBelow =
                viewportHeight -
                (referenceRect.y + referenceRect.height) -
                padding

              // Determine max height based on our custom logic:
              // 1. If enough space below, use space below
              // 2. If not enough space below, position from top with equal padding
              let maxHeight
              if (spaceBelow >= minSpaceThreshold) {
                // Enough space below, limit to space below
                maxHeight = Math.min(availableHeight, spaceBelow)
              } else {
                // Not enough space below, position from top with 10px padding at top and bottom
                maxHeight = Math.min(
                  availableHeight,
                  viewportHeight - 2 * padding,
                )
              }

              // Calculate width - minimum 300px or reference width, whichever is larger
              const minWidth = 300
              const referenceWidth = referenceRect.width
              const desiredWidth = Math.max(minWidth, referenceWidth)
              const maxWidth = Math.min(desiredWidth, availableWidth)

              // Apply dimensions to the dropdown container
              Object.assign(elements.floating.style, {
                maxHeight: `${maxHeight}px`,
                width: `${maxWidth}px`,
              })

              // Also set CSS custom properties that we can use for the inner menu
              elements.floating.style.setProperty(
                "--dropdown-max-height",
                `${maxHeight - 32}px`,
              ) // Account for padding
              elements.floating.style.setProperty(
                "--dropdown-width",
                `${maxWidth}px`,
              )
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

  // Handle clear search
  function clearSearch() {
    searchText = ""
    isSearching = false
    focusedIndex = 0
    if (searchInputElement) {
      searchInputElement.blur()
    }
  }

  // Handle key input when dropdown is open
  function handleKeyInput(event: KeyboardEvent) {
    // Don't interfere with navigation keys or if we're already focused on search input
    if (isSearching && document.activeElement === searchInputElement) {
      return
    }

    if (
      event.key === "ArrowDown" ||
      event.key === "ArrowUp" ||
      event.key === "Enter" ||
      event.key === "Escape" ||
      event.key === "Tab"
    ) {
      return
    }

    // If it's a printable character, start search mode
    if (
      event.key.length === 1 &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey
    ) {
      event.preventDefault()
      if (!isSearching) {
        isSearching = true
        searchText = event.key
        focusedIndex = 0
        // Focus the search input after it's rendered
        setTimeout(() => {
          if (searchInputElement) {
            searchInputElement.focus()
          }
        }, 0)
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
      document.addEventListener("keydown", handleKeyInput)
    } else {
      document.removeEventListener("click", handleDocumentClick)
      document.removeEventListener("keydown", handleKeyInput)
    }
  }
</script>

<div class="dropdown w-full relative">
  <div
    tabindex="0"
    role="listbox"
    class="select select-bordered w-full flex items-center {!listVisible
      ? 'focus:ring-2 focus:ring-offset-2 focus:ring-base-300'
      : ''}"
    bind:this={selectedElement}
    on:click={() => {
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
          filteredOptions.flatMap((group) => group.options).length - 1,
        )
        scrollToFocusedIndex()
      } else if (event.key === "ArrowUp") {
        event.preventDefault()
        focusedIndex = Math.max(focusedIndex - 1, 0)
        scrollToFocusedIndex()
      } else if (event.key === "Enter") {
        selectOption(
          filteredOptions.flatMap((group) => group.options)[focusedIndex].value,
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
      style="width: var(--dropdown-width, {selectedElement?.offsetWidth ||
        0}px); max-height: var(--dropdown-max-height, 300px);"
    >
      <!-- Search input - only show when searching -->
      {#if isSearching}
        <div
          class="flex items-center gap-2 p-2 border-b border-base-200 bg-base-100 mt-2"
        >
          <input
            bind:this={searchInputElement}
            bind:value={searchText}
            type="text"
            placeholder="Search..."
            class="input input-sm flex-1 focus:outline-none focus:ring-2 focus:ring-primary/50"
            on:keydown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault()
                clearSearch()
              } else if (event.key === "ArrowDown") {
                event.preventDefault()
                focusedIndex = Math.min(
                  focusedIndex + 1,
                  filteredOptions.flatMap((group) => group.options).length - 1,
                )
                scrollToFocusedIndex()
              } else if (event.key === "ArrowUp") {
                event.preventDefault()
                focusedIndex = Math.max(focusedIndex - 1, 0)
                scrollToFocusedIndex()
              } else if (event.key === "Enter") {
                event.preventDefault()
                const flatFiltered = filteredOptions.flatMap(
                  (group) => group.options,
                )
                if (flatFiltered[focusedIndex]) {
                  selectOption(flatFiltered[focusedIndex].value)
                }
              }
            }}
          />
          <button
            type="button"
            class="btn btn-ghost btn-sm btn-square"
            on:click={clearSearch}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      {/if}

      <ul
        class="menu overflow-y-auto overflow-x-hidden flex-nowrap pt-0 mt-2 custom-scrollbar flex-1"
        use:scrollableCheck
        style="max-height: calc(var(--dropdown-max-height, 300px) - {isSearching
          ? '4rem'
          : '1rem'});"
      >
        {#each filteredOptions as option, sectionIndex}
          <li class="menu-title pl-1 sticky top-0 bg-white z-10">
            {option.label}
          </li>
          {#each option.options as item, index}
            {@const overallIndex =
              filteredOptions
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

        <!-- Show "No results" message when filtering returns empty -->
        {#if isSearching && filteredOptions.length === 0}
          <li class="p-4 text-center text-base-content/60">
            No results found for "{searchText}"
          </li>
        {/if}
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
