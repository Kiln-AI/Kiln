<script lang="ts">
  import Chat from "./chat/chat.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import ChatIcon from "$lib/ui/icons/chat_icon.svelte"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import { getChatBarWidth, setChatBarWidth } from "$lib/chat/chat_ui_storage"
  import {
    chatBarExpanded,
    setChatBarExpanded,
  } from "$lib/stores/chat_ui_state"
  import { onDestroy, onMount } from "svelte"
  import { Section } from "$lib/ui/section"
  import { browser } from "$app/environment"
  import ChatCopilotRequired from "$lib/ui/kiln_copilot/chat_copilot_required.svelte"
  import {
    kilnCopilotConnected,
    initCopilotConnectionStore,
  } from "$lib/stores/copilot_connection_store"

  export let section: Section = Section.None

  const MIN_WIDTH = 280
  const MAX_WIDTH_VW = 30
  const DEFAULT_WIDTH_LG = 320
  const DEFAULT_WIDTH_2XL = 380
  const BREAKPOINT_2XL = 1536
  const RIGHT_MARGIN = 16

  $: expanded = $chatBarExpanded
  let dialog: Dialog
  let dialogOpen = false
  let customWidth: number | null = browser ? getChatBarWidth() : null
  let dragging = false

  type AnimState = "idle" | "collapsing" | "expanding"
  let animState: AnimState = "idle"

  function isLargeScreen(): boolean {
    return browser && window.matchMedia("(min-width: 1024px)").matches
  }

  function getDefaultWidth(): number {
    if (browser && window.innerWidth >= BREAKPOINT_2XL) {
      return DEFAULT_WIDTH_2XL
    }
    return DEFAULT_WIDTH_LG
  }

  $: sidebarWidth = customWidth ?? getDefaultWidth()

  function toggle() {
    if (isLargeScreen() && animState === "idle") {
      if (expanded) {
        animState = "collapsing"
        setChatBarExpanded(false)
      } else {
        animState = "expanding"
        setChatBarExpanded(true)
      }
    } else if (!isLargeScreen()) {
      setChatBarExpanded(!expanded)
    }
  }

  let iconBounce = false

  function onAnimationEnd() {
    if (animState === "collapsing") {
      iconBounce = true
      requestAnimationFrame(() => {
        setTimeout(() => {
          iconBounce = false
        }, 350)
      })
    }
    animState = "idle"
  }

  $: sidebarVisible = expanded || animState === "collapsing"

  $: iconHidden =
    expanded || animState === "collapsing" || animState === "expanding"

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

  let sidebarChat: Chat
  let dialogChat: Chat
  let sidebarHasMessages = false
  let dialogHasMessages = false

  onMount(() => {
    initCopilotConnectionStore()
  })

  $: copilot_chat_ready = $kilnCopilotConnected === true

  $: dialog_header_buttons = copilot_chat_ready
    ? [
        ...(dialogHasMessages
          ? [
              {
                image_path: "/images/new_chat.svg",
                alt_text: "New chat",
                action: () => dialogChat?.newChat(),
              },
            ]
          : []),
        {
          image_path: "/images/history.svg",
          alt_text: "Chat history",
          action: () => dialogChat?.openHistory(),
        },
      ]
    : []

  $: isChat = section === Section.Chat
</script>

{#if !isChat}
  <!-- Spacer to reserve width in the flex layout for the fixed sidebar -->
  {#if expanded}
    <div
      class="hidden lg:block flex-shrink-0"
      style:width="{sidebarWidth}px"
    ></div>
  {/if}

  <!-- Large screen sidebar: always in DOM on lg+, visibility controlled by animation -->
  <div
    class="hidden lg:flex flex-row fixed top-6 right-4 bottom-4 chat-anim-outer"
    class:chat-collapse-x={animState === "collapsing"}
    class:chat-expand-x={animState === "expanding"}
    class:chat-hidden={!sidebarVisible && animState === "idle"}
    style:width="{sidebarWidth}px"
    on:animationend={onAnimationEnd}
  >
    <div
      class="chat-anim-inner flex flex-row w-full h-full"
      class:chat-collapse-y={animState === "collapsing"}
      class:chat-expand-y={animState === "expanding"}
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
        class="rounded-3xl bg-base-100 shadow-md px-4 py-4 border flex flex-col flex-1 min-w-0 min-h-0 overflow-hidden"
      >
        <div class="flex flex-row items-center justify-between mb-4 shrink-0">
          <div class="text-lg font-medium">Chat</div>
          <div class="flex flex-row items-center gap-0.5">
            {#if copilot_chat_ready && sidebarHasMessages}
              <button
                class="btn btn-sm btn-circle btn-ghost"
                on:click={() => sidebarChat?.newChat()}
                aria-label="New chat"
                title="New chat"
              >
                <img
                  class="size-5"
                  src="/images/new_chat.svg"
                  alt="New chat"
                  aria-hidden="true"
                />
              </button>
            {/if}
            {#if copilot_chat_ready}
              <button
                class="btn btn-sm btn-circle btn-ghost"
                on:click={() => sidebarChat?.openHistory()}
                aria-label="Chat history"
                title="Chat history"
              >
                <img
                  class="size-5"
                  src="/images/history.svg"
                  alt="Chat history"
                  aria-hidden="true"
                />
              </button>
            {/if}
            <button
              class="btn btn-sm btn-circle btn-ghost"
              on:click={toggle}
              aria-label="Close chat sidebar"
            >
              <span class="size-5 block"><CloseIcon /></span>
            </button>
          </div>
        </div>
        <div class="flex flex-col flex-1 min-h-0 min-w-0">
          {#if $kilnCopilotConnected === null}
            <div class="flex-1 flex items-center justify-center min-h-[120px]">
              <span class="loading loading-spinner loading-md"></span>
            </div>
          {:else if $kilnCopilotConnected === false}
            <ChatCopilotRequired compact />
          {:else}
            <Chat
              bind:this={sidebarChat}
              bind:hasMessages={sidebarHasMessages}
            />
          {/if}
        </div>
      </div>
    </div>
  </div>

  <!-- Floating chat button -->
  <button
    class="fixed bottom-6 right-6 btn btn-circle btn-primary shadow-lg z-50 {iconHidden
      ? 'lg:hidden'
      : ''} {iconBounce ? 'chat-icon-bounce' : ''}"
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
  <Dialog
    bind:this={dialog}
    title="Chat"
    on:close={() => (dialogOpen = false)}
    width="wide"
    header_buttons={dialog_header_buttons}
  >
    {#if dialogOpen}
      <div class="h-[70vh] flex flex-col min-h-0">
        {#if $kilnCopilotConnected === null}
          <div class="flex-1 flex items-center justify-center">
            <span class="loading loading-spinner loading-lg"></span>
          </div>
        {:else if $kilnCopilotConnected === false}
          <ChatCopilotRequired compact />
        {:else}
          <Chat bind:this={dialogChat} bind:hasMessages={dialogHasMessages} />
        {/if}
      </div>
    {/if}
  </Dialog>
{/if}

<style>
  .drag-handle {
    width: 16px;
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

  .chat-hidden {
    visibility: hidden;
    pointer-events: none;
  }

  .chat-anim-outer {
    transform-origin: bottom right;
  }

  .chat-collapse-x,
  .chat-expand-x {
    overflow: hidden;
    will-change: transform, opacity;
  }

  .chat-anim-inner {
    transform-origin: bottom right;
  }

  .chat-collapse-y,
  .chat-expand-y {
    will-change: transform, opacity;
  }

  .chat-collapse-x {
    animation: collapse-x 400ms linear forwards;
  }

  .chat-collapse-y {
    animation:
      collapse-y 400ms linear forwards,
      collapse-opacity 250ms linear forwards;
  }

  .chat-expand-x {
    animation: expand-x 250ms linear forwards;
  }

  .chat-expand-y {
    animation:
      expand-y 250ms linear forwards,
      expand-opacity 250ms linear forwards;
  }

  @keyframes collapse-x {
    from {
      transform: translateX(0);
    }
    to {
      transform: translateX(calc(100% - 48px));
    }
  }

  @keyframes collapse-y {
    from {
      transform: translateY(0) scale(1);
    }
    to {
      transform: translateY(calc(100% - 48px)) scale(0.3);
    }
  }

  @keyframes collapse-opacity {
    0% {
      opacity: 1;
    }
    70% {
      opacity: 0;
    }
    100% {
      opacity: 0;
    }
  }

  @keyframes expand-x {
    from {
      transform: translateX(calc(100% - 48px));
    }
    to {
      transform: translateX(0);
    }
  }

  @keyframes expand-y {
    from {
      transform: translateY(calc(100% - 48px)) scale(0.3);
    }
    to {
      transform: translateY(0) scale(1);
    }
  }

  .chat-icon-bounce {
    animation: icon-bounce 350ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
  }

  @keyframes icon-bounce {
    0% {
      transform: scale(0.3);
    }
    60% {
      transform: scale(1.1);
    }
    100% {
      transform: scale(1);
    }
  }

  @keyframes expand-opacity {
    from {
      opacity: 0.5;
    }
    to {
      opacity: 1;
    }
  }
</style>
