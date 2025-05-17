<script lang="ts">
  import type { OptionGroup } from "./fancy_select_types"

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
  const id = Math.random().toString(36).substring(2, 15)

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
  } // Watch for changes to options and recheck scrollability
  $: options, setTimeout(checkIfScrollable, 0)

  // Set the dropdown top when the list is made
  $: if (listVisible) {
    updateDropdownTop()
  }

  function updateDropdownTop() {
    if (dropdownElement && selectedElement) {
      const rect = selectedElement.getBoundingClientRect()
      dropdownElement.style.setProperty("--dropdown-top", `${rect.top}px`)
    }
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

  // Clean up interval on component destruction
  import { onDestroy } from "svelte"
  onDestroy(() => {
    stopScroll()
  })

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
    on:blur={() => {
      listVisible = false
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

    <div
      class="dropdown-content relative bg-base-100 rounded-box z-[1] w-full p-2 pt-0 shadow absolute max-h-[50vh] flex flex-col relative border {listVisible
        ? 'block'
        : 'hidden'}"
      style="bottom: auto; left: 0; top: 0; max-height: calc(100vh - var(--dropdown-top, 0px) - 30px);"
      bind:this={dropdownElement}
    >
      <ul
        class="menu overflow-y-auto overflow-x-hidden flex-nowrap pt-0 mt-2 custom-scrollbar"
        use:scrollableCheck
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
  </div>
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
