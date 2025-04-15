<script lang="ts">
  import type { OptionGroup } from "./fancy_select_types"

  export let options: OptionGroup[] = []
  export let selected: unknown

  // Add this variable to track scrollability
  let isMenuScrollable = false
  let menuElement: HTMLElement
  let dropdownElement: HTMLElement
  let selectedElement: HTMLElement
  let scrolling = false
  let scrollInterval: number | null = null

  // Select a prompt
  function selectOption(option: unknown) {
    selected = option
    dropdownElement.blur()
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

  // Toggle dropdown
  function toggleSelectedElement(event: MouseEvent) {
    // If the element is already focused when clicked, prevent default focus behavior
    // and blur it instead
    if (document.activeElement === selectedElement) {
      event.preventDefault()
      selectedElement.blur()
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
</script>

<div class="dropdown w-full relative">
  <div
    tabindex="0"
    role="button"
    class="select select-bordered w-full flex items-center"
    bind:this={selectedElement}
    on:mousedown={toggleSelectedElement}
  >
    <span class="truncate">
      {(() => {
        const flatOptions = options.flatMap((group) => group.options)
        const selectedOption = flatOptions.find(
          (item) => item.value === selected,
        )
        return selectedOption ? selectedOption.label : ""
      })()}
    </span>
  </div>

  <!--svelte-ignore a11y-no-noninteractive-tabindex -->
  <div
    tabindex="0"
    class="dropdown-content relative bg-base-100 rounded-box z-[1] w-full p-2 pt-0 shadow absolute max-h-[50vh] flex flex-col relative"
    style="bottom: auto; top: 100%; max-height: min(50vh, calc(100vh - var(--dropdown-top, 0px) - 20px));"
    bind:this={dropdownElement}
  >
    <ul
      class="menu overflow-y-auto overflow-x-hidden flex-nowrap pt-0 mt-2"
      use:scrollableCheck
    >
      {#each options as option}
        <li class="menu-title pl-1 sticky top-0 bg-white z-10">
          {option.label}
        </li>
        {#each option.options as item}
          <li>
            <button
              class="flex flex-col text-left gap-[1px]"
              on:click={() => selectOption(item.value)}
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
        class="absolute bottom-0 left-0 right-0 pointer-events-auto rounded-b-md stroke-[2px] hover:stroke-[4px]"
        on:mouseenter={startScroll}
        on:mouseleave={stopScroll}
      >
        <div
          class="bg-gradient-to-b from-transparent to-white mx-3 w-full flex justify-center items-center py-1 cursor-pointer"
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
