<script lang="ts">
  import Chat from "./chat/chat.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import ChatIcon from "$lib/ui/icons/chat_icon.svelte"
  import {
    getChatBarExpanded,
    setChatBarExpanded,
    getChatBarWidth,
    setChatBarWidth,
  } from "$lib/chat/chat_ui_storage"
  import { onDestroy } from "svelte"
  import { Section } from "$lib/ui/section"
  import { browser } from "$app/environment"

  export let section: Section = Section.None

  const MIN_WIDTH = 280
  const MAX_WIDTH_VW = 50
  const DEFAULT_WIDTH_LG = 320
  const DEFAULT_WIDTH_2XL = 380
  const BREAKPOINT_2XL = 1536
  const RIGHT_MARGIN = 16

  let expanded = browser ? getChatBarExpanded() : true
  let dialog: Dialog
  let dialogOpen = false
  let customWidth: number | null = browser ? getChatBarWidth() : null
  let dragging = false

  function getDefaultWidth(): number {
    if (browser && window.innerWidth >= BREAKPOINT_2XL) {
      return DEFAULT_WIDTH_2XL
    }
    return DEFAULT_WIDTH_LG
  }

  $: sidebarWidth = customWidth ?? getDefaultWidth()

  function toggle() {
    expanded = !expanded
    setChatBarExpanded(expanded)
  }

  function getMaxWidth(): number {
    return Math.floor(window.innerWidth * (MAX_WIDTH_VW / 100))
  }

  function clampWidth(width: number): number {
    return Math.round(Math.max(MIN_WIDTH, Math.min(width, getMaxWidth())))
  }

  function onDragStart(e: MouseEvent) {
    e.preventDefault()
    dragging = true
    document.body.style.userSelect = "none"
    document.body.style.cursor = "col-resize"
    window.addEventListener("mousemove", onDragMove)
    window.addEventListener("mouseup", onDragEnd)
  }

  function onDragMove(e: MouseEvent) {
    if (!dragging) return
    const rightEdge = window.innerWidth
    const newWidth = rightEdge - e.clientX - RIGHT_MARGIN
    customWidth = clampWidth(newWidth)
  }

  function onDragEnd() {
    if (!dragging) return
    dragging = false
    document.body.style.userSelect = ""
    document.body.style.cursor = ""
    window.removeEventListener("mousemove", onDragMove)
    window.removeEventListener("mouseup", onDragEnd)
    if (customWidth !== null) {
      setChatBarWidth(customWidth)
    }
  }

  onDestroy(() => {
    if (dragging) {
      onDragEnd()
    }
  })

  function openDialog() {
    dialogOpen = true
    dialog?.show()
  }

  $: isChat = section === Section.Chat
</script>

{#if !isChat}
  <!-- Large screen sidebar -->
  {#if expanded}
    <!-- Spacer to reserve width in the flex layout for the fixed sidebar -->
    <div
      class="hidden lg:block flex-shrink-0"
      style:width="{sidebarWidth}px"
    ></div>
    <div
      class="hidden lg:flex flex-row fixed top-6 right-4 bottom-4"
      style:width="{sidebarWidth}px"
    >
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div
        class="drag-handle flex-shrink-0 flex items-center justify-center"
        role="none"
        on:mousedown={onDragStart}
      >
        <div class="drag-indicator"></div>
      </div>
      <div
        class="rounded-3xl bg-base-100 shadow-md px-4 py-8 border flex flex-col flex-1 min-w-0 min-h-0 overflow-y-auto"
      >
        <div class="flex flex-row items-center justify-between mb-4">
          <div class="text-lg font-medium">Chat</div>
          <button
            class="btn btn-sm btn-circle btn-ghost"
            on:click={toggle}
            aria-label="Close chat sidebar"
          >
            <svg
              class="h-5 w-5"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M7 7L17 17M7 17L17 7"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>
        <Chat />
      </div>
    </div>
  {/if}

  <!-- Floating chat button: on small screens always shows (opens dialog), on lg+ only when collapsed (expands sidebar) -->
  <button
    class="fixed bottom-6 right-6 btn btn-circle btn-primary shadow-lg z-50 {expanded
      ? 'lg:hidden'
      : ''}"
    on:click={() => {
      if (window.matchMedia("(min-width: 1024px)").matches) {
        toggle()
      } else {
        openDialog()
      }
    }}
    aria-label="Open chat"
  >
    <div class="w-6 h-6">
      <ChatIcon />
    </div>
  </button>

  <!-- Small screen dialog -->
  <Dialog bind:this={dialog} title="Chat" on:close={() => (dialogOpen = false)}>
    {#if dialogOpen}
      <Chat />
    {/if}
  </Dialog>
{/if}

<style>
  .drag-handle {
    width: 8px;
    cursor: col-resize;
    flex-shrink: 0;
  }

  .drag-handle:hover .drag-indicator,
  .drag-handle:active .drag-indicator {
    opacity: 1;
  }

  .drag-indicator {
    width: 4px;
    height: 32px;
    border-radius: 2px;
    background-color: oklch(var(--bc) / 0.25);
    opacity: 0;
    transition: opacity 150ms ease;
  }
</style>
