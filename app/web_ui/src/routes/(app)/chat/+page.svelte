<script lang="ts">
  import { getContext, onDestroy, onMount } from "svelte"
  import type { Writable } from "svelte/store"
  import AppPage from "../app_page.svelte"
  import Chat from "./chat.svelte"
  import { agentInfo } from "$lib/agent"
  import type { ActionButton } from "$lib/types"
  import ChatCopilotRequired from "$lib/ui/kiln_copilot/chat_copilot_required.svelte"
  import {
    kilnCopilotConnected,
    initCopilotConnectionStore,
  } from "$lib/stores/copilot_connection_store"

  agentInfo.set({
    name: "Chat",
    description: "The chat interface for conversing with the AI assistant.",
  })

  let chatRef: Chat
  let hasMessages = false

  $: action_buttons =
    $kilnCopilotConnected !== true
      ? ([] as ActionButton[])
      : [
          ...(hasMessages
            ? [
                {
                  icon: "/images/new_chat.svg",
                  handler: () => chatRef?.newChat(),
                } as ActionButton,
              ]
            : []),
          {
            icon: "/images/history.svg",
            handler: () => chatRef?.openHistory(),
          },
        ]

  const noLayoutBottomPadding = getContext<Writable<boolean>>(
    "noLayoutBottomPadding",
  )
  noLayoutBottomPadding.set(true)
  onDestroy(() => noLayoutBottomPadding.set(false))

  onMount(() => {
    initCopilotConnectionStore()
  })
</script>

<AppPage title="Chat" no_y_padding={true} {action_buttons}>
  <div class="flex flex-col h-[calc(100vh-8rem)] pt-4">
    {#if $kilnCopilotConnected === null}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $kilnCopilotConnected === false}
      <ChatCopilotRequired />
    {:else}
      <Chat bind:this={chatRef} bind:hasMessages />
    {/if}
  </div>
</AppPage>
