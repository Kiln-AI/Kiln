<script lang="ts">
  import Chat from "./chat/chat.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import ChatIcon from "$lib/ui/icons/chat_icon.svelte"
  import {
    getChatBarExpanded,
    setChatBarExpanded,
  } from "$lib/chat/chat_ui_storage"
  import { Section } from "$lib/ui/section"
  import { browser } from "$app/environment"

  export let section: Section = Section.None

  let expanded = browser ? getChatBarExpanded() : true
  let dialog: Dialog
  let dialogOpen = false
  let sidebarWidth = 320

  function toggle() {
    expanded = !expanded
    setChatBarExpanded(expanded)
  }

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
      class="hidden lg:flex flex-col fixed top-6 right-4 bottom-4"
      style:width="{sidebarWidth}px"
    >
      <div
        class="rounded-3xl bg-base-100 shadow-md px-4 py-8 border flex-1 min-h-0 overflow-y-auto"
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
