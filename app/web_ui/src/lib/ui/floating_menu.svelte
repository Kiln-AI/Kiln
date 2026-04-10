<script lang="ts">
  import Float from "$lib/ui/float.svelte"
  import type { Placement } from "@floating-ui/dom"
  import type { FloatingMenuItem } from "./floating_menu_types"
  import { onDestroy, onMount } from "svelte"

  export let items: FloatingMenuItem[]
  export let placement: Placement = "bottom-end"
  export let width: string = "w-52"
  export let hover: boolean = false

  let isOpen = false
  let wrapperElement: HTMLElement
  let leaveTimeout: ReturnType<typeof setTimeout> | null = null
  let mounted = false

  $: visibleItems = items.filter((item) => !item.hidden)
  $: hasVisibleItems = visibleItems.length > 0

  function toggle() {
    isOpen = !isOpen
  }

  function close() {
    isOpen = false
  }

  function handleItemClick(event: MouseEvent, item: FloatingMenuItem) {
    event.stopPropagation()
    if (item.onclick) {
      item.onclick()
    }
    close()
  }

  function handleMouseEnter() {
    if (!hover) return
    if (leaveTimeout) {
      clearTimeout(leaveTimeout)
      leaveTimeout = null
    }
    isOpen = true
  }

  function handleMouseLeave() {
    if (!hover) return
    leaveTimeout = setTimeout(() => {
      isOpen = false
      leaveTimeout = null
    }, 100)
  }

  function getClickToCloseElement(): Document | Element {
    const topModal = [...document.querySelectorAll("dialog[open]")].pop()
    return topModal ? topModal : document
  }

  function handleCloseElementClick(event: Event) {
    if (
      isOpen &&
      wrapperElement &&
      !wrapperElement.contains(event.target as Node)
    ) {
      close()
    }
  }

  let targetCloseElement: Document | Element | null = null
  $: if (mounted) {
    targetCloseElement?.removeEventListener("click", handleCloseElementClick)
    if (isOpen) {
      targetCloseElement = getClickToCloseElement()
      targetCloseElement.addEventListener("click", handleCloseElementClick)
    } else {
      targetCloseElement = null
    }
  }

  onMount(() => {
    mounted = true
  })

  onDestroy(() => {
    targetCloseElement?.removeEventListener("click", handleCloseElementClick)
    if (leaveTimeout) {
      clearTimeout(leaveTimeout)
    }
  })
</script>

{#if hasVisibleItems}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="relative inline-block"
    bind:this={wrapperElement}
    on:mouseenter={handleMouseEnter}
    on:mouseleave={handleMouseLeave}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <div on:click|stopPropagation={toggle}>
      <slot name="trigger" />
    </div>
    {#if isOpen}
      <Float {placement} strategy="fixed">
        <ul class="menu bg-base-100 rounded-box p-2 shadow {width}">
          {#each visibleItems as item}
            <li>
              {#if item.href}
                <a
                  href={item.href}
                  on:click|stopPropagation={() => {
                    item.onclick?.()
                    close()
                  }}
                >
                  {item.label}
                </a>
              {:else}
                <button on:click={(e) => handleItemClick(e, item)}>
                  {item.label}
                </button>
              {/if}
            </li>
          {/each}
        </ul>
      </Float>
    {/if}
  </div>
{/if}
